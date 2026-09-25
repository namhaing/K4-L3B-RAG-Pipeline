"""
Task 7 — Reciprocal Rank Fusion.

RRF gộp nhiều bảng xếp hạng mà không cộng trực tiếp cosine score với BM25
score. Công thức: RRF(d) = sum(1 / (k + rank)), rank bắt đầu từ 1.

Lưu ý: RRF score chỉ phản ánh thứ hạng, không dùng để quyết định fallback.

-> Dùng Jina hoặc self host hoặc bất cứ công cụ nào bạn quen
"""


def rerank_rrf(
    ranked_lists: list[list[dict]],
    top_k: int = 5,
    k: int = 60,
) -> list[dict]:
    """Fuse nhiều ranked lists và trả hybrid SearchResult."""
    if top_k <= 0:
        return []

    scores: dict[str, float] = {}
    items: dict[str, dict] = {}
    for ranked_list in ranked_lists:
        seen_in_list = set()
        for rank, item in enumerate(ranked_list, 1):
            item_id = item["id"]
            # Một ID chỉ được tính một lần trong mỗi danh sách (lấy rank tốt nhất).
            if item_id in seen_in_list:
                continue
            seen_in_list.add(item_id)
            scores[item_id] = scores.get(item_id, 0.0) + 1 / (k + rank)
            # Giữ bản đầu tiên gặp (dense đứng trước) làm nội dung/metadata.
            items.setdefault(item_id, item)

    ranked_ids = sorted(scores, key=scores.get, reverse=True)
    return [
        {**items[item_id], "score": scores[item_id], "retrieval_method": "hybrid"}
        for item_id in ranked_ids[:top_k]
    ]


RERANK_SYSTEM = """Bạn xếp hạng các đoạn văn bản pháp luật theo mức độ giúp trả lời câu hỏi của chủ hộ kinh doanh.
Ưu tiên đoạn chứa trực tiếp quy định trả lời câu hỏi; đoạn chỉ trùng từ khoá nhưng nói về đối tượng khác
(ví dụ doanh nghiệp, công ty) xếp sau. Trả về JSON {"ranking": [số thứ tự đoạn, từ liên quan nhất đến ít nhất]}."""
RERANK_PASSAGE_CHARS = 700


def rerank_llm(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Listwise rerank (kiểu RankGPT): LLM đọc cả danh sách ứng viên sau RRF và xếp lại.

    Score mới = 1/rank (chỉ để sort, giữ retrieval_method="hybrid"). Nếu LLM lỗi hoặc
    trả JSON hỏng thì giữ nguyên thứ tự RRF; ứng viên LLM bỏ sót được nối vào cuối.
    """
    if top_k <= 0 or not candidates:
        return []
    import json

    from .llm_client import chat

    passages = "\n\n".join(
        f"[{index}] {item['content'][:RERANK_PASSAGE_CHARS]}" for index, item in enumerate(candidates)
    )
    try:
        reply = chat(RERANK_SYSTEM, f"Câu hỏi: {query}\n\nCác đoạn:\n{passages}", json_mode=True, max_tokens=200)
        ranking = json.loads(reply).get("ranking", [])
    except Exception:
        return candidates[:top_k]

    order = []
    for index in ranking:
        if isinstance(index, int) and 0 <= index < len(candidates) and index not in order:
            order.append(index)
    order += [index for index in range(len(candidates)) if index not in order]
    return [
        {**candidates[index], "score": 1.0 / rank, "retrieval_method": "hybrid"}
        for rank, index in enumerate(order[:top_k], 1)
    ]


if __name__ == "__main__":
    import sys

    from .task5_semantic_search import semantic_search
    from .task6_lexical_search import lexical_search

    query = " ".join(sys.argv[1:]) or "Nghị định 123/2020 quy định gì về hoá đơn?"
    dense = semantic_search(query, top_k=10)
    sparse = lexical_search(query, top_k=10)
    dense_ids = {item["id"] for item in dense}
    sparse_ids = {item["id"] for item in sparse}
    for result in rerank_rrf([dense, sparse], top_k=5):
        found_by = "+".join(
            name for name, ids in (("dense", dense_ids), ("bm25", sparse_ids))
            if result["id"] in ids
        )
        print(f"{result['score']:.5f}  [{found_by}]  {result['id']}")
