import json

import pytest

from src.contracts import validate_search_results


def result(index: int, score: float, method: str = "hybrid", content: str | None = None) -> dict:
    return {
        "id": f"chunk-{index}",
        "content": content or f"Nội dung đoạn {index}",
        "score": score,
        "metadata": {"source": "doc.md", "title": "Văn bản", "doc_type": "legal", "url": None, "chunk_index": index},
        "retrieval_method": method,
    }


def test_rerank_llm_reorders_by_llm_ranking(monkeypatch):
    import src.llm_client as llm_client
    from src.task7_reranking import rerank_llm

    candidates = [result(index, 0.03 - index / 1000) for index in range(4)]
    monkeypatch.setattr(llm_client, "chat", lambda *args, **kwargs: json.dumps({"ranking": [2, 0, 2, 9]}))
    output = rerank_llm("câu hỏi", candidates, top_k=3)

    validate_search_results(output, top_k=3, expected_method="hybrid")
    # Chỉ số trùng (2) và ngoài phạm vi (9) bị bỏ; ứng viên LLM bỏ sót nối vào cuối theo thứ tự RRF.
    assert [item["id"] for item in output] == ["chunk-2", "chunk-0", "chunk-1"]
    assert [item["id"] for item in candidates] == ["chunk-0", "chunk-1", "chunk-2", "chunk-3"]


@pytest.mark.parametrize("reply", ["không phải json", RuntimeError("api down")])
def test_rerank_llm_keeps_rrf_order_on_failure(monkeypatch, reply):
    import src.llm_client as llm_client
    from src.task7_reranking import rerank_llm

    def fake_chat(*args, **kwargs):
        if isinstance(reply, Exception):
            raise reply
        return reply

    candidates = [result(index, 0.03 - index / 1000) for index in range(4)]
    monkeypatch.setattr(llm_client, "chat", fake_chat)
    assert [item["id"] for item in rerank_llm("q", candidates, top_k=2)] == ["chunk-0", "chunk-1"]


def test_hyde_query_appends_passage_and_falls_back(monkeypatch):
    import src.query_expansion as expansion

    monkeypatch.setattr(expansion, "chat", lambda *args, **kwargs: "Hộ kinh doanh đăng ký tại cơ quan đăng ký kinh doanh cấp huyện.")
    assert expansion.hyde_query("mở quán cần gì").startswith("mở quán cần gì\nHộ kinh doanh")

    def broken(*args, **kwargs):
        raise RuntimeError("api down")

    monkeypatch.setattr(expansion, "chat", broken)
    assert expansion.hyde_query("mở quán cần gì") == "mở quán cần gì"


@pytest.fixture
def pipeline(monkeypatch):
    import src.task9_retrieval_pipeline as pipeline

    calls = {"dense_queries": [], "fallback": 0}

    def fake_dense(query, top_k):
        calls["dense_queries"].append(query)
        # Câu hỏi gốc có cosine thấp hơn đoạn HyDE; threshold phải dùng cosine của câu gốc.
        return [result(0, 0.45 if query == "q" else 0.9, "dense")]

    def fake_fallback(query, top_k):
        calls["fallback"] += 1
        return []

    monkeypatch.setattr(pipeline, "semantic_search", fake_dense)
    monkeypatch.setattr(pipeline, "lexical_search", lambda query, top_k: [result(1, 5.0, "bm25")])
    monkeypatch.setattr(pipeline, "pageindex_search", fake_fallback)
    return pipeline, calls


def test_retrieve_with_llm_reranker_fuses_once_then_reranks(pipeline, monkeypatch):
    pipeline, _ = pipeline
    import src.task7_reranking as reranking

    seen = {}

    def fake_rrf(lists, top_k):
        seen.setdefault("rrf_calls", []).append(top_k)
        return [result(0, 0.03), result(1, 0.02)]

    def fake_rerank(query, candidates, top_k):
        seen["rerank_pool"] = len(candidates)
        return [{**candidates[1], "score": 1.0}, {**candidates[0], "score": 0.5}][:top_k]

    monkeypatch.setattr(pipeline, "RERANKER", "llm")
    monkeypatch.setattr(pipeline, "rerank_rrf", fake_rrf)
    monkeypatch.setattr(reranking, "rerank_llm", fake_rerank)

    output = pipeline.retrieve("q", top_k=2, score_threshold=0.3)
    assert seen["rrf_calls"] == [pipeline.RERANK_POOL]
    assert [item["id"] for item in output] == ["chunk-1", "chunk-0"]


def test_retrieve_with_hyde_uses_original_query_for_threshold(pipeline, monkeypatch):
    pipeline, calls = pipeline
    import src.query_expansion as expansion

    monkeypatch.setattr(pipeline, "QUERY_EXPANSION", "hyde")
    monkeypatch.setattr(expansion, "hyde_query", lambda query: f"{query}\nđoạn giả định")

    pipeline.retrieve("q", top_k=2, score_threshold=0.5)
    assert calls["dense_queries"] == ["q", "q\nđoạn giả định"]
    # cosine câu gốc 0.45 < 0.5 nên vẫn thử fallback, dù dense của HyDE đạt 0.9.
    assert calls["fallback"] == 1
