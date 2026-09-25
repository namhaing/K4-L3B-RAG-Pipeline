"""
Task 6 — Lexical search bằng BM25.

Dùng cùng corpus chunks với Task 5. BM25 phù hợp với từ khóa chính xác, mã tài
liệu và tên riêng. Output phải theo SearchResult và sort score giảm dần.

BM25 chấm trên phần thân chunk (bỏ nhãn văn bản Task 4 gắn ở đầu). Tokenizer giữ
nguyên số hiệu văn bản ("123/2020/nđ-cp") làm một token, đồng
thời thêm các phần con ("123", "2020", "nđ", "cp") để query "Nghị định
123/2020" vẫn khớp với văn bản ghi đầy đủ "123/2020/NĐ-CP".
"""

import math
import re
import unicodedata


CORPUS: list[dict] = []

_TOKEN = re.compile(r"\w+(?:[/\-.]\w+)*")
_SUBTOKEN = re.compile(r"[/\-.]")

_bm25_cache: dict = {"corpus": None, "index": None}


def tokenize(text: str) -> list[str]:
    """Lowercase + NFC, giữ số hiệu văn bản và bổ sung các phần con của nó."""
    tokens = []
    for token in _TOKEN.findall(unicodedata.normalize("NFC", text).lower()):
        tokens.append(token)
        if _SUBTOKEN.search(token):
            tokens.extend(part for part in _SUBTOKEN.split(token) if part)
    return tokens


def build_bm25_index(corpus: list[dict]):
    """Tạo BM25 index từ cùng corpus chunks của Task 4."""
    from rank_bm25 import BM25Okapi

    class _BM25(BM25Okapi):
        # IDF của BM25Okapi gốc bằng 0 khi term xuất hiện ở đúng nửa corpus và
        # âm khi nhiều hơn; dùng IDF kiểu Lucene log(1 + ...) luôn dương.
        def _calc_idf(self, nd):
            for word, freq in nd.items():
                self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    return _BM25([tokenize(_bm25_text(item)) for item in corpus])


def _bm25_text(item: dict) -> str:
    """Nội dung chunk bỏ nhãn văn bản ở đầu (Task 4 ghi độ dài vào ``prefix_chars``).

    Nhãn "Thông tư 40/2021/TT-BTC" có mặt ở mọi chunk của văn bản nên không giúp phân
    biệt chunk; giữ lại thì chunk ngắn chỉ chứa nhãn + tiêu đề được BM25 chấm cao.
    """
    return item["content"][item["metadata"].get("prefix_chars", 0):]


def _get_corpus() -> list[dict]:
    global CORPUS
    if not CORPUS:
        from .task4_chunking_indexing import load_indexed_chunks

        CORPUS = load_indexed_chunks()
    return CORPUS


def _get_index(corpus: list[dict]):
    if _bm25_cache["corpus"] is not corpus:
        _bm25_cache["corpus"] = corpus
        _bm25_cache["index"] = build_bm25_index(corpus)
    return _bm25_cache["index"]


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """Trả về BM25 SearchResult theo score giảm dần."""
    query_tokens = tokenize(query)
    if top_k <= 0 or not query_tokens:
        return []
    corpus = _get_corpus()
    if not corpus:
        return []

    scores = _get_index(corpus).get_scores(query_tokens)
    ranked = sorted(range(len(corpus)), key=lambda index: scores[index], reverse=True)

    results = []
    seen = set()
    for index in ranked:
        if len(results) >= top_k or scores[index] <= 0:
            break
        item = corpus[index]
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        results.append({
            "id": item["id"],
            "content": item["content"],
            "score": float(scores[index]),
            "metadata": item["metadata"],
            "retrieval_method": "bm25",
        })
    return results


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) or "Thông tư 40/2021/TT-BTC"
    for result in lexical_search(query, top_k=3):
        print(f"{result['score']:.4f}  {result['id']}\n    {result['content'][:150]!r}")
