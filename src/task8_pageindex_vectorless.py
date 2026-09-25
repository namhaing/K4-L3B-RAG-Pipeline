"""
Task 8 — PageIndex vectorless fallback.

Hướng dẫn:
    1. Đọc PAGEINDEX_API_KEY từ .env.
    2. Upload tài liệu ở định dạng PageIndex hỗ trợ.
    3. Cache document IDs để không upload lại.
    4. Parse kết quả thành SearchResult có method pageindex.

PageIndex là dịch vụ ngoài: cần timeout và xử lý lỗi để pipeline không crash.

Luồng theo SDK `pageindex` 0.2.8 (`PageIndexClient`):
    submit_document(pdf) -> {"doc_id"}          # chỉ nhận PDF: upload bản PDF gốc ở data/landing/legal
    is_retrieval_ready(doc_id) -> bool          # tài liệu cần vài phút để dựng cây mục lục
    submit_query(doc_id, query) -> {"retrieval_id"}
    get_retrieval(retrieval_id) -> {"status": "processing" | "completed",   # endpoint đã deprecated nhưng vẫn chạy
                                    "retrieved_nodes": [{"title", "id",
                                        "relevant_contents": [[{"section_title", "physical_index", "relevant_content"}]]}]}

SDK gọi `requests` không có timeout, nên toàn bộ một lần search chạy trong thread
riêng và bị bỏ sau SEARCH_TIMEOUT giây; lỗi hoặc hết giờ đều trả [] để Task 9 dùng
kết quả hybrid.

    python -m src.task8_pageindex_vectorless     # upload PDF, chờ sẵn sàng, chạy thử 1 query
"""

import json
import logging
import os
import re
import threading
import time
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
LEGAL_PDF_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"
CACHE_FILE = Path(__file__).parent.parent / "pageindex_doc_ids.json"

SEARCH_TIMEOUT = 45.0   # giây cho cả một lần pageindex_search
POLL_INTERVAL = 2.0     # giây giữa hai lần hỏi trạng thái retrieval


def _client():
    """PageIndexClient, hoặc None khi chưa cấu hình key."""
    if not PAGEINDEX_API_KEY:
        return None
    from pageindex import PageIndexClient

    return PageIndexClient(api_key=PAGEINDEX_API_KEY)


def _load_cache() -> dict[str, str]:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def upload_documents() -> dict[str, str]:
    """Upload PDF văn bản luật chưa có trong cache; trả về {tên file (stem): doc_id}.

    Chỉ ghi vào cache những file upload thành công, nên lần chạy sau sẽ thử lại
    file bị lỗi thay vì kẹt với cache rỗng.
    """
    doc_ids = _load_cache()
    client = _client()
    if client is None:
        logger.warning("PAGEINDEX_API_KEY chưa cấu hình, bỏ qua upload PageIndex")
        return doc_ids

    for pdf in sorted(LEGAL_PDF_DIR.glob("*.pdf")):
        if pdf.stem in doc_ids:
            continue
        try:
            doc_ids[pdf.stem] = str(client.submit_document(str(pdf))["doc_id"])
            CACHE_FILE.write_text(json.dumps(doc_ids, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Uploaded %s -> %s", pdf.name, doc_ids[pdf.stem])
        except Exception as error:
            logger.warning("Upload %s lên PageIndex thất bại: %s", pdf.name, error)
    return doc_ids


def _legal_metadata() -> dict[str, dict]:
    """Metadata theo contract (source, title, doc_type, url, doc_number) của từng văn bản,
    lấy từ header Markdown chuẩn hoá để citation của PageIndex giống kết quả hybrid."""
    from .task4_chunking_indexing import load_documents

    return {
        Path(doc["metadata"]["source"]).stem: doc["metadata"]
        for doc in load_documents()
        if doc["metadata"]["doc_type"] == "legal"
    }


def _node_contents(node: dict) -> list[dict]:
    """relevant_contents thật là list lồng list ([[{...}]]); tài liệu cũ ghi list phẳng."""
    items = []
    for entry in node.get("relevant_contents") or []:
        items.extend(entry if isinstance(entry, list) else [entry])
    return [item for item in items if isinstance(item, dict)]


def _node_page(item: dict) -> int | None:
    """Trang của đoạn trích: "page_index" (số) hoặc "physical_index" dạng "<physical_index_80>"."""
    value = item.get("page_index", item.get("physical_index"))
    digits = re.search(r"\d+", str(value)) if value is not None else None
    return int(digits.group()) if digits else None


def _node_text(node: dict) -> str:
    parts = [item.get("relevant_content", "") for item in _node_contents(node)]
    return "\n".join(part.strip() for part in parts if part and part.strip()) or (node.get("text") or "").strip()


def _to_results(stem: str, nodes: list[dict], metadata: dict) -> list[dict]:
    """Chuyển retrieved_nodes của một văn bản thành SearchResult.

    PageIndex không trả score: dùng 1/rank theo thứ tự PageIndex xếp trong văn bản
    đó. Score này chỉ để sort, không so sánh được với cosine.
    """
    base = metadata.get(stem) or {"source": f"{stem}.pdf", "title": stem, "doc_type": "legal", "url": None}
    results = []
    for rank, node in enumerate(nodes, 1):
        text = _node_text(node)
        if not text:
            continue
        title = (node.get("title") or "").strip()
        pages = [page for page in map(_node_page, _node_contents(node)) if page is not None]
        node_metadata = {**base, "chunk_index": rank - 1}
        if title:
            node_metadata["article"] = title[:100]
        if pages:
            node_metadata["page"] = pages[0]
        results.append({
            "id": f"pageindex::{stem}::{node.get('node_id') or node.get('id') or rank}",
            "content": f"{title}\n{text}" if title and not text.startswith(title) else text,
            "score": 1.0 / rank,
            "metadata": node_metadata,
            "retrieval_method": "pageindex",
        })
    return results


def _search(query: str, top_k: int, deadline: float) -> list[dict]:
    client = _client()
    if client is None:
        return []
    doc_ids = upload_documents()
    metadata = _legal_metadata()

    pending = {}
    for stem, doc_id in doc_ids.items():
        if not client.is_retrieval_ready(doc_id):
            logger.info("PageIndex %s (%s) chưa sẵn sàng, bỏ qua", stem, doc_id)
            continue
        pending[stem] = client.submit_query(doc_id, query)["retrieval_id"]

    results = []
    while pending and time.monotonic() < deadline:
        for stem, retrieval_id in list(pending.items()):
            response = client.get_retrieval(retrieval_id)
            if response.get("status") == "completed":
                results += _to_results(stem, response.get("retrieved_nodes") or [], metadata)
                del pending[stem]
            elif response.get("status") == "failed":
                logger.warning("PageIndex retrieval %s thất bại", retrieval_id)
                del pending[stem]
        if pending:
            time.sleep(POLL_INTERVAL)
    if pending:
        logger.warning("PageIndex hết thời gian chờ cho %s", ", ".join(pending))

    unique = {}
    for result in sorted(results, key=lambda item: item["score"], reverse=True):
        unique.setdefault(result["id"], result)
    return list(unique.values())[:top_k]


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """Trả về pageindex SearchResult theo score giảm dần, không quá top_k.

    Không bao giờ raise: thiếu key, lỗi mạng/API hay hết SEARCH_TIMEOUT đều trả [].
    """
    if top_k <= 0 or not query.strip() or not PAGEINDEX_API_KEY:
        return []

    box: dict = {}

    def worker() -> None:
        try:
            box["results"] = _search(query, top_k, time.monotonic() + SEARCH_TIMEOUT)
        except Exception as error:  # SDK raise PageIndexAPIError / requests exceptions
            box["error"] = error

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(SEARCH_TIMEOUT)
    if thread.is_alive():
        logger.warning("PageIndex không phản hồi sau %.0fs, dùng kết quả hybrid", SEARCH_TIMEOUT)
        return []
    if "error" in box:
        logger.warning("PageIndex search thất bại: %s", box["error"])
        return []
    return box.get("results", [])


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    if not PAGEINDEX_API_KEY:
        raise SystemExit("Điền PAGEINDEX_API_KEY vào .env trước.")
    ids = upload_documents()
    client = _client()
    for stem, doc_id in ids.items():
        print(f"{stem}: {doc_id} ready={client.is_retrieval_ready(doc_id)}")
    query = " ".join(sys.argv[1:]) or "Hồ sơ đăng ký hộ kinh doanh gồm những gì?"
    for result in pageindex_search(query, top_k=3):
        print(f"{result['score']:.3f}  {result['id']}  {result['metadata'].get('article', '')}")
        print("    ", result["content"][:200].replace("\n", " "))
