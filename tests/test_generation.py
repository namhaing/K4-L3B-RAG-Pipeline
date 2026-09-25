import pytest

from src.contracts import validate_generation_result


def result(index: int, method: str = "hybrid") -> dict:
    return {
        "id": f"chunk-{index}",
        "content": f"Nội dung điều {index}.",
        "score": 1 - index / 10,
        "metadata": {
            "source": f"doc-{index}.md",
            "title": f"Văn bản {index}",
            "doc_type": "legal",
            "url": None,
            "chunk_index": index,
        },
        "retrieval_method": method,
    }


@pytest.fixture
def generation(monkeypatch):
    import src.task10_generation as generation

    chunks = [result(index) for index in range(4)]
    monkeypatch.setattr(generation, "retrieve", lambda query, top_k, use_reranking: chunks)
    return generation


def test_citations_are_remapped_to_sources_order(generation, monkeypatch):
    # Context sau reorder: [chunk-0, chunk-2, chunk-3, chunk-1].
    monkeypatch.setattr(
        generation, "call_llm", lambda system, user: "A [Document 2]. B [Document 4]. C [Document 9]."
    )
    output = generation.generate_with_citation("thuế hộ kinh doanh", top_k=4)

    validate_generation_result(output)
    assert output["retrieval_source"] == "hybrid"
    assert generation.extract_citations(output["answer"]) == [3, 2]
    assert "[Document 9]" not in output["answer"]
    assert generation.DISCLAIMER in output["answer"]


def test_dense_only_config_maps_to_hybrid_source(generation, monkeypatch):
    dense = [result(0, "dense")]
    monkeypatch.setattr(generation, "retrieve", lambda query, top_k, use_reranking: dense)
    monkeypatch.setattr(generation, "call_llm", lambda system, user: "Trả lời [Document 1].")

    output = generation._generate("thuế", top_k=1, use_reranking=False)
    validate_generation_result(output)
    assert output["retrieval_source"] == "hybrid"


def test_provider_error_returns_safe_refusal(generation, monkeypatch):
    def unavailable(system, user):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(generation, "call_llm", unavailable)
    output = generation.generate_with_citation("thuế", top_k=4)

    validate_generation_result(output)
    assert output == {"answer": generation.REFUSAL_MESSAGE, "sources": [], "retrieval_source": "none"}


def test_empty_retrieval_returns_safe_refusal(generation, monkeypatch):
    monkeypatch.setattr(generation, "retrieve", lambda query, top_k, use_reranking: [])
    output = generation.generate_with_citation("giá vàng hôm nay", top_k=4)

    validate_generation_result(output)
    assert output["retrieval_source"] == "none"
