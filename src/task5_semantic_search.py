"""
Task 5 — Semantic search.

Embed query bằng chính hàm của Task 4, query ChromaDB và đổi cosine distance
thành similarity. Output phải theo SearchResult, sort giảm dần và không quá top_k.
"""

from .task4_chunking_indexing import embed_texts, get_collection


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """Trả về dense SearchResult theo score giảm dần.

    score = 1 - cosine distance: đây là cosine score gốc mà Task 9 dùng để
    quyết định fallback, không được chuẩn hoá hay thay bằng score khác.
    """
    if top_k <= 0 or not query.strip():
        return []

    query_vector = embed_texts([query])[0]
    response = get_collection().query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    results = {}
    for item_id, content, metadata, distance in zip(
        response["ids"][0],
        response["documents"][0],
        response["metadatas"][0],
        response["distances"][0],
    ):
        if item_id in results:
            continue
        results[item_id] = {
            "id": item_id,
            "content": content,
            "score": max(0.0, 1.0 - float(distance)),
            # Chroma không lưu None nên url bị bỏ khi index; khôi phục theo contract.
            "metadata": {"url": None, **metadata},
            "retrieval_method": "dense",
        }
    ranked = sorted(results.values(), key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) or "Doanh thu bao nhiêu thì hộ kinh doanh phải nộp thuế?"
    for result in semantic_search(query, top_k=3):
        print(f"{result['score']:.4f}  {result['id']}\n    {result['content'][:150]!r}")
