"""
Task 1 — Thu thập tài liệu chính sách/quy định gốc từ nguồn .gov.vn.

Nguồn: bản đăng Công báo (congbao.chinhphu.vn). Bản "signed" trên
vanban.chinhphu.vn là PDF scan không có lớp text nên MarkItDown không đọc được;
bản Công báo là PDF dàn trang có text đầy đủ.
Nếu tải lỗi thì báo lỗi, không ghi nội dung thay thế.
"""

from pathlib import Path

import requests


DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"

SOURCES = {
    "tt-40-2021-tt-btc-thue-ho-kinh-doanh.pdf":
        "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/6/33850/36037-1-2021649-65040-2021-tt-btc.pdf",
    "nd-01-2021-nd-cp-dang-ky-doanh-nghiep-hkd.pdf":
        "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/1/32981/34281-1-2021113-11401-2021-nd-cp.pdf",
    # Công báo số 1011+1012 chứa toàn bộ 61 Điều; số 1013+1014 chỉ là phụ lục mẫu biểu.
    "nd-123-2020-nd-cp-hoa-don-chung-tu.pdf":
        "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2020/10/32290/32999-1-20201011-1012123-2020-nd-cp.pdf",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def setup_directory() -> None:
    """Tạo thư mục lưu tài liệu gốc."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Ready: {DATA_DIR}")


def download_documents() -> None:
    """Tải PDF gốc; bỏ qua file đã có để chạy lại không tải trùng."""
    setup_directory()
    for filename, url in SOURCES.items():
        path = DATA_DIR / filename
        if path.exists() and path.read_bytes()[:5] == b"%PDF-":
            print(f"Skip (exists): {filename}")
            continue
        try:
            response = requests.get(url, headers=HEADERS, timeout=300)
            response.raise_for_status()
            if not response.content.startswith(b"%PDF-"):
                raise ValueError("response is not a PDF")
            path.write_bytes(response.content)
            print(f"Downloaded: {filename} ({len(response.content):,} bytes)")
        except Exception as error:
            print(f"FAILED {filename} from {url}: {error}")
            print(f"  -> tải thủ công file PDF vào {DATA_DIR}")


if __name__ == "__main__":
    download_documents()
