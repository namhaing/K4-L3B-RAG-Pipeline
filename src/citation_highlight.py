"""
Tô sáng đoạn nguồn được trích dẫn (bonus UI).

Với mỗi [Document n] trong câu trả lời, lấy câu/ý chứa citation đó rồi tìm câu
trong nội dung nguồn n có nhiều từ khoá trùng nhất. app.py dùng các vị trí trả
về để bọc <mark>, giúp người dùng thấy ngay Điều/Khoản nào đã được dùng.

Chỉ so khớp từ vựng (không gọi LLM) nên chạy tức thì và kiểm thử được offline.
"""

import re
import unicodedata


_CITATION = re.compile(r"\[Document\s+(\d+)\]", re.IGNORECASE)
_WORD = re.compile(r"\w+")
_ANSWER_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_LINE = re.compile(r"[^\n]+")
_SENTENCE = re.compile(r".+?(?:[.;!?](?=\s)|$)")

# Hư từ tiếng Việt phổ biến: bỏ đi để điểm trùng phản ánh nội dung, không phải ngữ pháp.
STOPWORDS = {
    "và", "của", "các", "là", "có", "được", "cho", "theo", "với", "trong", "thì",
    "không", "phải", "này", "đó", "khi", "từ", "đến", "một", "những", "về", "hoặc",
    "do", "tại", "để", "nếu", "như", "trên", "dưới", "bao", "nhiêu", "gì", "nào",
    "đã", "sẽ", "cũng", "vẫn", "mà", "nên", "thể", "việc", "người", "quy", "định",
}


def _tokens(text: str) -> set[str]:
    words = _WORD.findall(unicodedata.normalize("NFC", text).lower())
    return {word for word in words if word not in STOPWORDS and (len(word) > 1 or word.isdigit())}


def claims_by_citation(answer: str) -> dict[int, list[str]]:
    """Map n -> các câu trong câu trả lời có trích dẫn [Document n] (đã bỏ citation)."""
    claims: dict[int, list[str]] = {}
    for sentence in _ANSWER_SPLIT.split(answer):
        numbers = [int(n) for n in _CITATION.findall(sentence)]
        if not numbers:
            continue
        text = _CITATION.sub("", sentence).strip(" -*•_\t")
        for n in dict.fromkeys(numbers):
            claims.setdefault(n, []).append(text)
    return claims


def _sentences(content: str) -> list[tuple[int, int]]:
    spans = []
    for line in _LINE.finditer(content):
        for sentence in _SENTENCE.finditer(line.group()):
            start = line.start() + sentence.start()
            end = line.start() + sentence.end()
            if content[start:end].strip():
                spans.append((start, end))
    return spans


def supporting_spans(
    content: str,
    claims: list[str],
    min_overlap: float = 0.35,
    min_shared: int = 3,
) -> list[tuple[int, int]]:
    """Vị trí (start, end) các câu trong content khớp tốt nhất với từng claim.

    Một câu được chọn khi chia sẻ >= min_overlap số từ khoá của claim và ít nhất
    min_shared từ (hoặc toàn bộ từ khoá nếu claim ngắn hơn). Kết quả đã sort và gộp.
    """
    sentences = [(start, end, _tokens(content[start:end])) for start, end in _sentences(content)]
    chosen = set()
    for claim in claims:
        claim_tokens = _tokens(claim)
        if len(claim_tokens) < 2:
            continue
        best, best_ratio, best_shared = None, 0.0, 0
        for start, end, sentence_tokens in sentences:
            shared = len(claim_tokens & sentence_tokens)
            ratio = shared / len(claim_tokens)
            if ratio > best_ratio:
                best, best_ratio, best_shared = (start, end), ratio, shared
        if best and best_ratio >= min_overlap and best_shared >= min(min_shared, len(claim_tokens)):
            chosen.add(best)

    merged: list[tuple[int, int]] = []
    for start, end in sorted(chosen):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged
