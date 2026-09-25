"""
Task 9 — Retrieval pipeline hoàn chỉnh.

Luồng xử lý:
    1. Chạy semantic_search và lexical_search.
    2. Fuse hai danh sách bằng RRF đúng một lần.
    3. Lấy best cosine score gốc từ dense results.
    4. Nếu score dưới threshold, thử PageIndex fallback.
    5. Nếu fallback lỗi, trả hybrid results thay vì crash.

Không so sánh threshold với RRF score vì hai thang đo khác nhau.
"""

import logging
import os

from dotenv import load_dotenv

from .task5_semantic_search import semantic_search
from .task6_lexical_search import lexical_search
from .task7_reranking import rerank_rrf
from .task8_pageindex_vectorless import pageindex_search


load_dotenv()

logger = logging.getLogger(__name__)


def _threshold_from_env(default: float = 0.3) -> float:
    """Đọc SCORE_THRESHOLD đã calibrate; .env để trống thì dùng default."""
    raw = os.getenv("SCORE_THRESHOLD", "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        logger.warning("SCORE_THRESHOLD=%r không phải số, dùng %s", raw, default)
        return default


SCORE_THRESHOLD = _threshold_from_env()
DEFAULT_TOP_K = 5


def _safe_search(search_fn, query: str, top_k: int) -> list[dict]:
    """Một retriever lỗi (chưa index, thiếu model) không được kéo sập cả pipeline."""
    try:
        return search_fn(query, top_k=top_k) or []
    except Exception:
        logger.exception("%s failed", getattr(search_fn, "__name__", search_fn))
        return []


def retrieve(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float = SCORE_THRESHOLD,
    use_reranking: bool = True,
) -> list[dict]:
    """Trả về hybrid hoặc pageindex SearchResult.

    use_reranking=False là Config A (dense-only) cho A/B: bỏ BM25 và RRF,
    nhưng vẫn giữ cùng logic threshold/fallback để so sánh công bằng.
    """
    if not query or not query.strip() or top_k <= 0:
        return []

    candidate_k = top_k * 2
    dense = _safe_search(semantic_search, query, candidate_k)

    if use_reranking:
        sparse = _safe_search(lexical_search, query, candidate_k)
        candidates = rerank_rrf([dense, sparse], top_k=top_k)
    else:
        candidates = dense[:top_k]

    # Threshold so với cosine gốc của dense, không phải RRF score.
    best_dense_score = dense[0]["score"] if dense else 0.0
    if best_dense_score < score_threshold:
        try:
            fallback = pageindex_search(query, top_k=top_k)
            if fallback:
                return fallback[:top_k]
        except Exception:
            logger.exception("PageIndex fallback failed, returning hybrid results")

    return candidates[:top_k]


if __name__ == "__main__":
    for result in retrieve("test query", top_k=3):
        print(result)
