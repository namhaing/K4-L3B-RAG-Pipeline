"""
HyDE (Hypothetical Document Embeddings) cho dense search.

Câu hỏi văn nói ("mở quán cà phê cần giấy tờ gì") khác xa văn phong văn bản luật nên
cosine thấp. HyDE nhờ LLM viết một đoạn giả định theo văn phong quy định pháp luật,
rồi embed "câu hỏi + đoạn giả định" để tìm chunk. Đoạn giả định có thể sai nội dung;
nó chỉ dùng để tìm kiếm, không đưa vào context trả lời.
"""

from .llm_client import chat


HYDE_SYSTEM = """Viết một đoạn ngắn (3–5 câu) theo văn phong điều khoản văn bản pháp luật Việt Nam
(nghị định, thông tư về hộ kinh doanh, thuế, hóa đơn) có thể trả lời câu hỏi. Dùng thuật ngữ pháp lý
chính thức (hộ kinh doanh, cơ quan đăng ký kinh doanh cấp huyện, thuế GTGT, thuế TNCN, hóa đơn điện tử...).
Chỉ viết đoạn văn, không giải thích."""


def hyde_query(query: str) -> str:
    """Trả về "câu hỏi + đoạn giả định" để embed; LLM lỗi thì trả về câu hỏi gốc."""
    try:
        passage = chat(HYDE_SYSTEM, query, max_tokens=250)
    except Exception:
        return query
    return f"{query}\n{passage}" if passage else query
