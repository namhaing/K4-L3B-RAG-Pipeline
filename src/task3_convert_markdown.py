"""
Task 3 — Chuẩn hóa dữ liệu sang Markdown.

- Legal: PDF Công báo -> MarkItDown -> bỏ dòng đầu trang Công báo -> thêm header.
- News: JSON -> header (title, Source, Ngày đăng, Crawled) + content_markdown.
Header theo mẫu trong docs/TEAM_PLAN.md để Task 4 đọc ra metadata.
Chạy lại ghi đè file cũ và xoá Markdown không còn file landing tương ứng.
"""

import json
import re
from pathlib import Path


LANDING_DIR = Path(__file__).parent.parent / "data" / "landing"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "standardized"

# Metadata lấy từ trang văn bản trên vanban.chinhphu.vn / Công báo (kiểm tra 25/09/2026).
LEGAL_METADATA = {
    "tt-40-2021-tt-btc-thue-ho-kinh-doanh": {
        "title": "Thông tư 40/2021/TT-BTC hướng dẫn thuế giá trị gia tăng, thuế thu nhập cá nhân "
                 "và quản lý thuế đối với hộ kinh doanh, cá nhân kinh doanh",
        "source": "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/6/33850/36037-1-2021649-65040-2021-tt-btc.pdf",
        "doc_number": "40/2021/TT-BTC",
        "issued_date": "2021-06-01",
        "effective": "Có hiệu lực từ 01/08/2021; được sửa đổi, bổ sung bởi Thông tư 100/2021/TT-BTC. "
                     "Chính sách thuế hộ kinh doanh thay đổi từ 01/01/2026, cần đối chiếu quy định mới.",
    },
    "nd-01-2021-nd-cp-dang-ky-doanh-nghiep-hkd": {
        # Tên chính thức. Không thêm "(Chương VIII: đăng ký hộ kinh doanh)": cụm này bị lặp
        # vào mọi chunk của văn bản khiến dense/BM25 không phân biệt được Chương VIII.
        "title": "Nghị định 01/2021/NĐ-CP về đăng ký doanh nghiệp",
        "source": "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/1/32981/34281-1-2021113-11401-2021-nd-cp.pdf",
        "doc_number": "01/2021/NĐ-CP",
        "issued_date": "2021-01-04",
        "effective": "Có hiệu lực từ 04/01/2021; hết hiệu lực từ 01/07/2025.",
    },
    "nd-123-2020-nd-cp-hoa-don-chung-tu": {
        "title": "Nghị định 123/2020/NĐ-CP quy định về hóa đơn, chứng từ",
        "source": "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2020/10/32290/32999-1-20201011-1012123-2020-nd-cp.pdf",
        "doc_number": "123/2020/NĐ-CP",
        "issued_date": "2020-10-19",
        "effective": "Có hiệu lực từ 01/07/2022; được sửa đổi, bổ sung bởi Nghị định 70/2025/NĐ-CP.",
    },
}

# Phần mẫu biểu cuối văn bản (bảng xoay, trích xuất ra chữ ngược) -> cắt bỏ.
# TT40 giữ Phụ lục I (danh mục ngành nghề + tỷ lệ % thuế), bỏ từ "Mẫu số" trở đi.
CUT_FROM = {
    "tt-40-2021-tt-btc-thue-ho-kinh-doanh": r"^\s*Mẫu số",
    "nd-123-2020-nd-cp-hoa-don-chung-tu": r"^\s*Phụ lục IA\b",
}

# Dòng đầu trang Công báo ("CÔNG BÁO/Số 113 + 114/Ngày 24-01-2021 3"), kể cả khi
# MarkItDown bọc nó thành một hàng bảng, và dòng phân cách bảng rỗng đi kèm.
_NOISE_LINE = re.compile(
    r"^.*CÔNG BÁO/Số.*$|^\s*VĂN BẢN QUY PHẠM PHÁP LUẬT\s*$|^[\s|:-]*\|[\s|:-]*$",
    re.MULTILINE,
)
# Dòng mở đầu một mục mới: không nối vào dòng trước.
_BLOCK_START = re.compile(r"^(Điều \d+|Chương [IVXLC]+|Mục \d+|Phụ lục [IVXLC]+$|\d+\.\s|[a-zđ]\)\s|[-–•+|])")


def _unwrap_lines(text: str) -> str:
    """Nối dòng bị ngắt cứng giữa câu theo khổ trang PDF.

    Nối khi dòng trước chưa kết thúc câu và dòng sau bắt đầu bằng chữ thường
    hoặc chữ số (nhưng không phải mục "1." / "a)"). Dòng trống xen giữa câu
    (pdfminer hay chèn) cũng được bỏ qua trong trường hợp đó.
    """
    out: list[str] = []
    pending_blank = False
    for raw in text.split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", raw).strip()
        if not line:
            pending_blank = True
            continue
        prev = out[-1] if out else ""
        continues = (
            prev and prev[-1] not in ".:;!?" and not _BLOCK_START.match(line)
            and (line[0].islower() or line[0].isdigit())
        )
        if continues:
            out[-1] = f"{prev} {line}"
        else:
            if pending_blank and out:
                out.append("")
            out.append(line)
        pending_blank = False
    return "\n".join(out)


def _clean_pdf_text(text: str, cut_from: str | None = None) -> str:
    text = text.replace("\f", "\n")
    if cut_from:
        # Chỉ tìm điểm cắt sau Điều cuối cùng để không cắt nhầm câu trong thân văn bản.
        articles = list(re.finditer(r"^Điều \d+\.", text, re.MULTILINE))
        start = articles[-1].start() if articles else 0
        match = re.compile(cut_from, re.MULTILINE).search(text, start)
        if match:
            text = text[:match.start()]
    text = _NOISE_LINE.sub("", text)
    # Bảng Phụ lục (danh mục ngành nghề, tỷ lệ thuế) -> text thường; giữ ký tự "|" thì
    # sinh ra chunk gần rỗng mà BM25 lại chấm cao nhờ chuẩn hoá độ dài.
    text = re.sub(r"[ \t]*\|[ \t|]*", " ", text)
    return re.sub(r"\n{3,}", "\n\n", _unwrap_lines(text)).strip()


def _write(path: Path, header: str, body: str) -> None:
    path.write_text(header + body.strip() + "\n", encoding="utf-8")
    print(f"Standardized: {path.parent.name}/{path.name} ({len(body):,} chars)")


def _remove_stale(output_dir: Path, keep: set[str]) -> None:
    for path in output_dir.glob("*.md"):
        if path.stem not in keep:
            path.unlink()
            print(f"Removed stale: {output_dir.name}/{path.name}")


def convert_legal_docs() -> None:
    """Convert PDF/DOCX vào standardized/legal."""
    from markitdown import MarkItDown

    legal_dir = LANDING_DIR / "legal"
    output_dir = OUTPUT_DIR / "legal"
    output_dir.mkdir(parents=True, exist_ok=True)
    converter = MarkItDown()

    converted = set()
    for path in sorted(legal_dir.iterdir()):
        if path.suffix.lower() not in {".pdf", ".docx"}:
            continue
        meta = LEGAL_METADATA.get(path.stem)
        if meta is None:
            print(f"SKIP {path.name}: chưa khai báo metadata trong LEGAL_METADATA")
            continue
        body = _clean_pdf_text(converter.convert(str(path)).text_content, CUT_FROM.get(path.stem))
        if len(body) < 1000:
            print(f"SKIP {path.name}: trích xuất được {len(body)} ký tự (PDF scan?)")
            continue
        header = (
            f"# {meta['title']}\n"
            f"**Source:** {meta['source']}\n"
            f"**Số hiệu:** {meta['doc_number']}\n"
            f"**Ngày ban hành:** {meta['issued_date']}\n"
            f"**Hiệu lực:** {meta['effective']}\n"
            f"---\n\n"
        )
        _write(output_dir / f"{path.stem}.md", header, body)
        converted.add(path.stem)
    _remove_stale(output_dir, converted)


def convert_news_articles() -> None:
    """Convert JSON vào standardized/news."""
    news_dir = LANDING_DIR / "news"
    output_dir = OUTPUT_DIR / "news"
    output_dir.mkdir(parents=True, exist_ok=True)

    converted = set()
    for path in sorted(news_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        header = f"# {data['title']}\n**Source:** {data['url']}\n"
        if data.get("published_date"):
            header += f"**Ngày đăng:** {data['published_date']}\n"
        header += f"**Crawled:** {data['date_crawled']}\n---\n\n"
        _write(output_dir / f"{path.stem}.md", header, data["content_markdown"])
        converted.add(path.stem)
    _remove_stale(output_dir, converted)


def convert_all() -> None:
    """Convert toàn bộ dữ liệu landing."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    convert_legal_docs()
    convert_news_articles()
    print(f"Saved Markdown to: {OUTPUT_DIR}")


if __name__ == "__main__":
    convert_all()
