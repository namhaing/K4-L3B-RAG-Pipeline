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


# Calibrate bằng `python -m src.calibrate_threshold` (text-embedding-3-small): 24 câu in-domain
# (16 golden + 8 văn nói, min 0.509) và 8 câu out/sát domain (max 0.551) -> đề xuất 0.497,
# accuracy 30/32. Xem group_project/evaluation/threshold_calibration.json. Đổi embedding model
# hoặc cách chunk thì phải calibrate lại.
CALIBRATED_THRESHOLD = 0.50


def _threshold_from_env(default: float = CALIBRATED_THRESHOLD) -> float:
    """Đọc SCORE_THRESHOLD đã calibrate; .env để trống thì dùng default."""
    raw = os.getenv("SCORE_THRESHOLD", "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        logger.warning("SCORE_THRESHOLD=%r không phải số, dùng %s", raw, default)
        return default


SCORE_THRESHOLD = _threshold_from_env()
DEFAULT_TOP_K = 5

# Bonus, mặc định tắt (bật trong .env hoặc run_eval config C/D):
#   RERANKER=llm          RRF lấy RERANK_POOL ứng viên rồi LLM xếp lại (rerank_llm, Task 7)
#   QUERY_EXPANSION=hyde  dense search bằng "câu hỏi + đoạn giả định" (query_expansion.hyde_query)
RERANKER = os.getenv("RERANKER", "none").strip().lower()
QUERY_EXPANSION = os.getenv("QUERY_EXPANSION", "none").strip().lower()
RERANK_POOL = 15


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
    # Threshold luôn tính trên cosine của câu hỏi gốc (giá trị đã calibrate), kể cả khi dùng HyDE.
    best_dense_score = dense[0]["score"] if dense else 0.0
    if QUERY_EXPANSION == "hyde":
        from .query_expansion import hyde_query

        dense = _safe_search(semantic_search, hyde_query(query), candidate_k) or dense

    if use_reranking:
        sparse = _safe_search(lexical_search, query, candidate_k)
        if RERANKER == "llm":
            from .task7_reranking import rerank_llm

            pool = rerank_rrf([dense, sparse], top_k=RERANK_POOL)
            candidates = rerank_llm(query, pool, top_k=top_k)
        else:
            candidates = rerank_rrf([dense, sparse], top_k=top_k)
    else:
        candidates = dense[:top_k]

    # Threshold so với cosine gốc của dense, không phải RRF score.
    if best_dense_score < score_threshold:
        try:
            fallback = pageindex_search(query, top_k=top_k)
            if fallback:
                return fallback[:top_k]
        except Exception as error:
            logger.warning("PageIndex fallback unavailable (%r), returning hybrid results", error)

    return candidates[:top_k]


if __name__ == "__main__":
    for result in retrieve("test query", top_k=3):
        print(result)
