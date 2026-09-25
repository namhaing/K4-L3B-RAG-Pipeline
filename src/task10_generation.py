"""
Task 10 — Generation có citation.

Hướng dẫn:
    1. Retrieve top-k chunks.
    2. Reorder để giảm lost-in-the-middle.
    3. Format context kèm title và source.
    4. Gọi provider được chọn trong .env.
    5. Trả answer, sources và retrieval_source.

Nếu context không đủ hoặc provider lỗi, trả safe refusal; không bịa thông tin.
"""

import logging
import os
import re

from dotenv import load_dotenv

from .task9_retrieval_pipeline import retrieve


load_dotenv()

logger = logging.getLogger(__name__)

TOP_K = 5
TOP_P = 0.9
TEMPERATURE = 0.3
MAX_OUTPUT_TOKENS = 1500
LLM_TIMEOUT_SECONDS = 60

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-sonnet-5",
}

REFUSAL_MESSAGE = "Tôi không thể xác minh thông tin này từ nguồn hiện có."
DISCLAIMER = "Thông tin chỉ mang tính tham khảo, không thay thế tư vấn pháp lý."

SYSTEM_PROMPT = f"""Bạn là trợ lý tra cứu pháp luật dành cho hộ kinh doanh cá thể tại Việt Nam \
(đăng ký hộ kinh doanh, thuế, kê khai, hoá đơn điện tử, bán hàng qua thương mại điện tử).

Quy tắc bắt buộc:
1. Chỉ trả lời dựa trên các tài liệu trong phần Context. Không dùng kiến thức bên ngoài, không suy đoán.
2. Mỗi ý phải kèm citation dạng [Document n], với n là số thứ tự tài liệu trong Context. \
Nhiều nguồn thì ghi riêng từng citation, ví dụ [Document 1][Document 3].
3. Khi trích văn bản pháp luật, nêu tên văn bản, số hiệu và Điều/Khoản nếu Context có \
(ví dụ: "theo Điều 4 Thông tư 40/2021/TT-BTC [Document 2]").
4. Nếu các nguồn mâu thuẫn (ví dụ bài báo cũ và quy định mới), ưu tiên văn bản pháp luật \
có hiệu lực mới hơn và nói rõ mốc thời gian áp dụng.
5. Nếu Context không đủ căn cứ, hoặc câu hỏi nằm ngoài phạm vi pháp luật cho hộ kinh doanh \
(ví dụ hôn nhân, hình sự, thuế của công ty/doanh nghiệp), trả lời đúng một câu: "{REFUSAL_MESSAGE}" \
rồi gợi ý ngắn gọn người dùng nên hỏi cơ quan nào.
6. Viết tiếng Việt, ngắn gọn, dễ hiểu với chủ hộ kinh doanh; dùng gạch đầu dòng khi liệt kê hồ sơ, bước hoặc tỷ lệ.
7. Kết thúc câu trả lời bằng dòng: "{DISCLAIMER}"
"""

# Bonus conversation memory: viết lại câu hỏi nối tiếp ("Còn bán online thì sao?")
# thành câu hỏi độc lập trước khi retrieve, vì retriever không thấy lịch sử chat.
HISTORY_MESSAGES = 6
CONDENSE_PROMPT = """Bạn viết lại câu hỏi cho hệ thống tra cứu pháp luật dành cho hộ kinh doanh.
Dựa vào lịch sử hội thoại, viết lại câu hỏi mới nhất thành MỘT câu hỏi độc lập, tự đủ nghĩa bằng tiếng Việt:
điền lại chủ thể, chủ đề, ngành nghề hoặc số hiệu văn bản đã nhắc ở các lượt trước.
Không trả lời câu hỏi và không thêm thông tin mới. Nếu câu hỏi đã độc lập thì giữ nguyên.
Chỉ in ra câu hỏi đã viết lại."""

# Cộng dồn token của mọi lần gọi LLM; run_eval.py lấy chênh lệch trước/sau mỗi câu.
LLM_USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

_CITATION_PATTERN = re.compile(r"\[Document\s+(\d+)\]", re.IGNORECASE)

# Thông tin mở rộng do Task 4 gắn vào metadata (nếu có), theo thứ tự hiển thị.
_CONTEXT_FIELDS = (
    ("doc_number", "Số hiệu"),
    ("article", "Điều"),
    ("issued_date", "Ngày ban hành"),
    ("effective_date", "Hiệu lực"),
    ("published_date", "Ngày đăng"),
)


def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """Đưa chunks quan trọng về đầu và cuối context."""
    if len(chunks) <= 2:
        return list(chunks)
    front = chunks[::2]
    back = chunks[1::2]
    return front + back[::-1]


def format_context(chunks: list[dict]) -> str:
    """Tạo context có title và source label."""
    parts = []
    for index, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        label = [f"Document {index}", f"Title: {metadata.get('title', 'Không rõ')}"]
        label.append(f"Loại: {'văn bản pháp luật' if metadata.get('doc_type') == 'legal' else 'bài viết'}")
        for key, name in _CONTEXT_FIELDS:
            value = metadata.get(key)
            if value not in (None, ""):
                label.append(f"{name}: {value}")
        label.append(f"Source: {metadata.get('source', 'Không rõ')}")
        if metadata.get("url"):
            label.append(f"URL: {metadata['url']}")
        parts.append(f"[{' | '.join(label)}]\n{chunk['content']}")
    return "\n\n---\n\n".join(parts)


def _require_key(env_name: str) -> str:
    key = os.getenv(env_name, "").strip()
    if not key:
        raise RuntimeError(f"Thiếu {env_name} trong .env")
    return key


def _record_usage(input_tokens: int | None, output_tokens: int | None) -> None:
    LLM_USAGE["calls"] += 1
    LLM_USAGE["input_tokens"] += input_tokens or 0
    LLM_USAGE["output_tokens"] += output_tokens or 0


def call_llm(system_prompt: str, user_message: str) -> str:
    """Gọi OpenAI, Gemini hoặc Anthropic theo cấu hình."""
    provider = LLM_PROVIDER
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"LLM_PROVIDER không hợp lệ: {provider!r} (openai | gemini | anthropic)")
    model = LLM_MODEL or DEFAULT_MODELS[provider]

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=_require_key("OPENAI_API_KEY"), timeout=LLM_TIMEOUT_SECONDS)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=TEMPERATURE,
            top_p=TOP_P,
            max_completion_tokens=MAX_OUTPUT_TOKENS,
        )
        usage = response.usage
        _record_usage(usage and usage.prompt_tokens, usage and usage.completion_tokens)
        return (response.choices[0].message.content or "").strip()

    if provider == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=_require_key("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=LLM_TIMEOUT_SECONDS * 1000),
        )
        response = client.models.generate_content(
            model=model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            ),
        )
        usage = response.usage_metadata
        _record_usage(usage and usage.prompt_token_count, usage and usage.candidates_token_count)
        return (response.text or "").strip()

    import anthropic

    client = anthropic.Anthropic(api_key=_require_key("ANTHROPIC_API_KEY"), timeout=LLM_TIMEOUT_SECONDS)
    # Model Claude mới không nhận đồng thời temperature và top_p, nên chỉ truyền temperature.
    response = client.messages.create(
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        temperature=TEMPERATURE,
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    _record_usage(response.usage.input_tokens, response.usage.output_tokens)
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _refusal() -> dict:
    return {"answer": REFUSAL_MESSAGE, "sources": [], "retrieval_source": "none"}


def _remap_citations(answer: str, reordered: list[dict], sources: list[dict]) -> str:
    """Đổi [Document n] theo thứ tự context sang thứ tự trong `sources`.

    Context được reorder, còn `sources` giữ thứ tự score giảm dần, nên số
    citation phải được dịch lại. Citation trỏ ra ngoài context bị bỏ.
    """
    position = {item["id"]: index for index, item in enumerate(sources, 1)}

    def replace(match: re.Match) -> str:
        n = int(match.group(1))
        if 1 <= n <= len(reordered):
            return f"[Document {position[reordered[n - 1]['id']]}]"
        logger.warning("Bỏ citation không hợp lệ [Document %s] (chỉ có %s nguồn)", n, len(reordered))
        return ""

    return _CITATION_PATTERN.sub(replace, answer)


def extract_citations(answer: str) -> list[int]:
    """Các số n (không trùng, theo thứ tự xuất hiện) trong [Document n]."""
    return list(dict.fromkeys(int(n) for n in _CITATION_PATTERN.findall(answer)))


def condense_question(query: str, history: list[dict] | None) -> str:
    """Viết lại câu hỏi nối tiếp thành câu độc lập dựa trên vài lượt chat gần nhất.

    history là list {"role": "user" | "assistant", "content": str}. LLM lỗi
    hoặc trả kết quả bất thường thì giữ nguyên câu hỏi gốc.
    """
    turns = [
        message for message in (history or [])
        if message.get("role") in ("user", "assistant") and str(message.get("content", "")).strip()
    ][-HISTORY_MESSAGES:]
    if not turns:
        return query

    lines = []
    for message in turns:
        text = _CITATION_PATTERN.sub("", message["content"]).replace(DISCLAIMER, "").strip(" _\n")
        speaker = "Người dùng" if message["role"] == "user" else "Trợ lý"
        lines.append(f"{speaker}: {text[:600]}")
    user_message = (
        "Lịch sử hội thoại:\n" + "\n".join(lines)
        + f"\n\nCâu hỏi mới nhất: {query}\n\nCâu hỏi độc lập:"
    )
    try:
        rewritten = call_llm(CONDENSE_PROMPT, user_message)
    except Exception:
        logger.exception("Condense question failed, using original query")
        return query

    lines = (rewritten or "").strip().splitlines()
    rewritten = lines[0].strip().strip('"“”') if lines else ""
    return rewritten if 0 < len(rewritten) <= 500 else query


def _generate(
    query: str,
    top_k: int = TOP_K,
    use_reranking: bool = True,
    history: list[dict] | None = None,
) -> dict:
    """Pipeline đầy đủ; use_reranking=False là Config A (dense-only) cho A/B.

    history (tuỳ chọn) bật conversation memory: câu hỏi được viết lại thành
    câu độc lập và trả kèm trong key "rewritten_query" nếu khác câu gốc.
    """
    if not query or not query.strip():
        return _refusal()

    query = query.strip()
    standalone = condense_question(query, history) if history else query
    result = _answer(standalone, top_k, use_reranking)
    if standalone != query:
        result["rewritten_query"] = standalone
    return result


def _answer(query: str, top_k: int, use_reranking: bool) -> dict:
    try:
        chunks = retrieve(query, top_k=top_k, use_reranking=use_reranking)
    except Exception:
        logger.exception("Retrieval failed")
        return _refusal()
    if not chunks:
        return _refusal()

    reordered = reorder_for_llm(chunks)
    user_message = f"Context:\n{format_context(reordered)}\n\nQuestion: {query}"
    try:
        answer = call_llm(SYSTEM_PROMPT, user_message)
    except Exception:
        logger.exception("LLM provider %s failed", LLM_PROVIDER)
        return _refusal()
    if not answer:
        return _refusal()

    answer = _remap_citations(answer, reordered, chunks)
    if REFUSAL_MESSAGE in answer and not extract_citations(answer):
        # LLM từ chối vì context không đủ căn cứ: không gắn nguồn không dùng tới vào câu
        # trả lời. "retrieved" giữ lại chunk đã xét để eval vẫn chấm được retrieval.
        return {"answer": answer, "sources": [], "retrieval_source": "none", "retrieved": chunks}
    if DISCLAIMER not in answer:
        answer = f"{answer}\n\n_{DISCLAIMER}_"

    # Config A trả retrieval_method="dense", nhưng GenerationResult chỉ nhận hybrid/pageindex/none.
    method = chunks[0]["retrieval_method"]
    return {
        "answer": answer,
        "sources": chunks,
        "retrieval_source": "pageindex" if method == "pageindex" else "hybrid",
    }


def generate_with_citation(query: str, top_k: int = TOP_K) -> dict:
    """Trả về GenerationResult."""
    return _generate(query, top_k=top_k, use_reranking=True)


if __name__ == "__main__":
    print(generate_with_citation("test query"))
