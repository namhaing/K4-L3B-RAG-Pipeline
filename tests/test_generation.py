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


def test_follow_up_question_is_condensed_before_retrieval(generation, monkeypatch):
    seen = {}

    def fake_retrieve(query, top_k, use_reranking):
        seen["query"] = query
        return [result(0)]

    def fake_llm(system, user):
        if system == generation.CONDENSE_PROMPT:
            assert "Tỷ lệ thuế với quán ăn" in user
            return "Tỷ lệ thuế với hộ kinh doanh bán hàng online là bao nhiêu?"
        return "Trả lời [Document 1]."

    monkeypatch.setattr(generation, "retrieve", fake_retrieve)
    monkeypatch.setattr(generation, "call_llm", fake_llm)
    history = [
        {"role": "user", "content": "Tỷ lệ thuế với quán ăn là bao nhiêu?"},
        {"role": "assistant", "content": "GTGT 3%, TNCN 1,5% [Document 1]."},
    ]
    output = generation._generate("Còn nếu bán online thì sao?", top_k=1, history=history)

    validate_generation_result(output)
    assert seen["query"] == "Tỷ lệ thuế với hộ kinh doanh bán hàng online là bao nhiêu?"
    assert output["rewritten_query"] == seen["query"]


def test_condense_falls_back_to_original_query_on_error(generation, monkeypatch):
    def unavailable(system, user):
        raise RuntimeError("timeout")

    monkeypatch.setattr(generation, "call_llm", unavailable)
    history = [{"role": "user", "content": "Thuế quán ăn?"}]
    assert generation.condense_question("Còn online?", history) == "Còn online?"


def test_supporting_span_matches_cited_claim():
    from src.citation_highlight import claims_by_citation, supporting_spans

    answer = (
        "Hộ có doanh thu từ 100 triệu đồng trở xuống không phải nộp thuế GTGT [Document 1].\n"
        "- Hồ sơ gồm giấy đề nghị đăng ký [Document 2]."
    )
    claims = claims_by_citation(answer)
    assert set(claims) == {1, 2}

    content = (
        "Điều 4. Nguyên tắc tính thuế\n"
        "1. Hộ kinh doanh có doanh thu trong năm dương lịch từ 100 triệu đồng trở xuống "
        "thì không phải nộp thuế GTGT. 2. Hộ khoán nộp thuế theo quý."
    )
    spans = supporting_spans(content, claims[1])
    assert len(spans) == 1
    assert "100 triệu đồng trở xuống" in content[spans[0][0]:spans[0][1]]
    assert supporting_spans(content, claims[2]) == []


def test_llm_refusal_drops_unused_sources(generation, monkeypatch):
    monkeypatch.setattr(
        generation, "call_llm",
        lambda system, user: f"{generation.REFUSAL_MESSAGE} Hãy hỏi Toà án nhân dân cấp huyện.",
    )
    output = generation.generate_with_citation("Thủ tục ly hôn thuận tình?", top_k=4)

    validate_generation_result(output)
    assert output["sources"] == [] and output["retrieval_source"] == "none"
    assert len(output["retrieved"]) == 4
