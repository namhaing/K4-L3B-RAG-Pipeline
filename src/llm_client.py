"""
Lời gọi LLM phụ cho retrieval (reranker, HyDE) — tách khỏi Task 10 để tránh import vòng.

Dùng OpenAI với cùng LLM_MODEL của nhóm (mặc định gpt-4o-mini). USAGE cộng dồn token
để evaluation tính được chi phí thêm của các bước này.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()

MODEL = os.getenv("LLM_MODEL", "").strip() or "gpt-4o-mini"
USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0}


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=30.0)


def chat(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 400) -> str:
    """Một lượt chat temperature 0; raise khi API lỗi để caller tự quyết định fallback."""
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    response = _client().chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        **kwargs,
    )
    USAGE["calls"] += 1
    if response.usage:
        USAGE["input_tokens"] += response.usage.prompt_tokens
        USAGE["output_tokens"] += response.usage.completion_tokens
    return (response.choices[0].message.content or "").strip()
