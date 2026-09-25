"""
Task 8 — PageIndex vectorless fallback.

Hướng dẫn:
    1. Đọc PAGEINDEX_API_KEY từ .env.
    2. Upload tài liệu ở định dạng PageIndex hỗ trợ.
    3. Cache document IDs để không upload lại.
    4. Parse kết quả thành SearchResult có method pageindex.

PageIndex là dịch vụ ngoài: cần timeout và xử lý lỗi để pipeline không crash.
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
CACHE_FILE = Path(__file__).parent.parent / "pageindex_doc_ids.json"


def upload_documents() -> dict[str, str]:
    """Upload tài liệu và lưu document IDs vào pageindex_doc_ids.json."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    doc_ids = {}
    if not PAGEINDEX_API_KEY:
        logger.warning("PAGEINDEX_API_KEY không được thiết lập trong .env")
        return doc_ids

    try:
        from pageindex import PageIndex
        client = PageIndex(api_key=PAGEINDEX_API_KEY)

        # Upload các file markdown từ standardized/legal và news
        legal_dir = STANDARDIZED_DIR / "legal"
        if legal_dir.exists():
            for md_file in legal_dir.glob("*.md"):
                try:
                    res = client.submit_document(file_path=str(md_file))
                    doc_id = getattr(res, "doc_id", None) or getattr(res, "id", str(md_file.stem))
                    doc_ids[md_file.name] = str(doc_id)
                except Exception as e:
                    logger.warning("Lỗi upload %s lên PageIndex: %s", md_file.name, e)

        CACHE_FILE.write_text(json.dumps(doc_ids, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as error:
        logger.warning("Không thể khởi tạo PageIndex SDK: %s", error)

    return doc_ids


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """Trả về pageindex SearchResult đúng chuẩn schema."""
    if not PAGEINDEX_API_KEY:
        logger.warning("PAGEINDEX_API_KEY chưa cài đặt, bỏ qua PageIndex fallback.")
        return []

    try:
        doc_ids_map = upload_documents()
        doc_ids = list(doc_ids_map.values())
        if not doc_ids:
            return []

        from pageindex import PageIndex
        client = PageIndex(api_key=PAGEINDEX_API_KEY)

        # Query PageIndex
        raw_results = client.search(query=query, doc_ids=doc_ids, top_k=top_k)
        results = []
        for rank, item in enumerate(raw_results or [], start=1):
            content = getattr(item, "text", "") or getattr(item, "content", str(item))
            doc_id = getattr(item, "doc_id", f"pageindex-{rank}")
            score = float(getattr(item, "score", 1.0 / rank))

            results.append({
                "id": f"pageindex::{doc_id}::{rank}",
                "content": content,
                "score": score,
                "metadata": {
                    "source": getattr(item, "source", "PageIndex"),
                    "title": getattr(item, "title", "PageIndex Document"),
                },
                "retrieval_method": "pageindex",
            })
        return results[:top_k]

    except Exception as error:
        logger.warning("PageIndex search thất bại: %s", error)
        return []


if __name__ == "__main__":
    upload_documents()

