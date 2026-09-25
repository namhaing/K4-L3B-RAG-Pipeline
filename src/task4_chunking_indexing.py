"""
Task 4 — Chunking, embedding và indexing.

Hướng dẫn:
    1. Đọc toàn bộ Markdown trong data/standardized/.
    2. Chia văn bản bằng strategy đã chọn.
    3. Embed chunks bằng một provider duy nhất.
    4. Upsert vào ChromaDB với cosine distance.

Mỗi document/chunk phải theo docs/MODULE_CONTRACTS.md. ID cần ổn định để
chạy lại pipeline không tạo dữ liệu trùng. Task 5 phải dùng chung embed_texts().

Strategy cho văn bản pháp luật: tách theo "Điều N" trước, Điều nào dài hơn
CHUNK_SIZE thì cắt tiếp bằng RecursiveCharacterTextSplitter và lặp lại tiêu đề
Điều ở đầu mỗi chunk con để chunk không mất ngữ cảnh. Bài báo chỉ dùng
recursive splitter. Mọi chunk đều mở đầu bằng tên văn bản/bài viết.
"""

import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"

# Một Khoản trong văn bản luật thường dài 200–600 ký tự: chunk 800 ký tự chứa
# trọn 1–3 Khoản; overlap 100 giữ câu nối giữa hai chunk của cùng một Điều.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
CHUNKING_METHOD = "legal_article+recursive"

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers")
_DEFAULT_MODELS = {
    "sentence_transformers": "BAAI/bge-m3",
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-001",
}
_DEFAULT_DIMS = {
    "BAAI/bge-m3": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "gemini-embedding-001": 3072,
}
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or _DEFAULT_MODELS.get(EMBEDDING_PROVIDER, "")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM") or _DEFAULT_DIMS.get(EMBEDDING_MODEL, 0))
EMBEDDING_BATCH_SIZE = 64

COLLECTION_NAME = "rag_documents"
UPSERT_BATCH_SIZE = 1000

# "**Source:** https://..." ở phần header do Task 3 sinh ra -> metadata key.
_HEADER_FIELDS = {
    "source": "url",
    "url": "url",
    "số hiệu": "doc_number",
    "ngày ban hành": "issued_date",
    "hiệu lực": "effective_date",
    "ngày đăng": "published_date",
    "crawled": "date_crawled",
}
_HEADER_LINE = re.compile(r"^\*\*(?P<key>[^*]+?):\*\*\s*(?P<value>.*)$")
# Tiêu đề Điều có dạng "Điều 4. Tên điều" ở đầu dòng; bắt buộc dấu chấm để không
# nhầm với dòng PDF bị ngắt giữa câu như "Điều 4 của Luật này...". Nhận cả
# "Dieu" vì một số PDF trích xuất ra văn bản mất dấu.
_ARTICLE_HEADING = re.compile(r"^[ \t#*]*((?:Điều|Dieu)[ \t]+\d+[a-z]?\..*)$", re.MULTILINE)
_ARTICLE_PREFIX_MAX = 100
_TITLE_PREFIX_MAX = 150


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n")


@lru_cache(maxsize=1)
def _sentence_transformer():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _openai_client():
    from openai import OpenAI

    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@lru_cache(maxsize=1)
def _gemini_client():
    from google import genai

    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _embed_batch(texts: list[str]) -> list[list[float]]:
    if EMBEDDING_PROVIDER == "sentence_transformers":
        vectors = _sentence_transformer().encode(texts, normalize_embeddings=True)
        return vectors.tolist()
    if EMBEDDING_PROVIDER == "openai":
        response = _openai_client().embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in response.data]
    if EMBEDDING_PROVIDER == "gemini":
        response = _gemini_client().models.embed_content(model=EMBEDDING_MODEL, contents=texts)
        return [list(item.values) for item in response.embeddings]
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed theo batch bằng provider trong .env; Task 5 dùng lại hàm này."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        vectors.extend(_embed_batch(texts[start:start + EMBEDDING_BATCH_SIZE]))
    if EMBEDDING_DIM and vectors and len(vectors[0]) != EMBEDDING_DIM:
        raise ValueError(
            f"{EMBEDDING_MODEL} trả về {len(vectors[0])} chiều, "
            f"EMBEDDING_DIM={EMBEDDING_DIM}; sửa EMBEDDING_DIM trong .env"
        )
    return vectors


def get_collection():
    """Mở Chroma collection dùng cosine distance."""
    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL},
    )
    indexed_model = (collection.metadata or {}).get("embedding_model")
    if indexed_model and indexed_model != EMBEDDING_MODEL:
        raise RuntimeError(
            f"Collection đã index bằng {indexed_model}, hiện đang dùng {EMBEDDING_MODEL}. "
            f"Xoá thư mục {CHROMA_DIR.name}/ rồi index lại."
        )
    return collection


def _parse_markdown(text: str) -> tuple[str | None, dict, str]:
    """Tách header (# Title, **Key:** value, ---) khỏi nội dung chính."""
    lines = text.split("\n")
    title = None
    fields: dict = {}
    body_start = 0
    for index, line in enumerate(lines[:30]):
        stripped = line.strip()
        if not stripped:
            continue
        if title is None and stripped.startswith("# "):
            title = stripped[2:].strip()
            body_start = index + 1
            continue
        match = _HEADER_LINE.match(stripped)
        if match:
            key = _HEADER_FIELDS.get(match["key"].strip().lower())
            if key and match["value"].strip():
                fields[key] = match["value"].strip()
            body_start = index + 1
            continue
        if stripped == "---" and (title or fields):
            body_start = index + 1
        break
    body = "\n".join(lines[body_start:]).strip()
    return title, fields, body or text.strip()


def load_documents() -> list[dict]:
    """Đọc Markdown và trả về danh sách Document."""
    documents = []
    for path in sorted(STANDARDIZED_DIR.rglob("*.md")):
        text = _normalize(path.read_text(encoding="utf-8"))
        if not text.strip():
            continue
        title, fields, body = _parse_markdown(text)
        relative = path.relative_to(STANDARDIZED_DIR)
        documents.append({
            "id": relative.as_posix(),
            "content": body,
            "metadata": {
                "source": path.name,
                "title": title or path.stem,
                "doc_type": "legal" if relative.parts[0] == "legal" else "news",
                "url": fields.pop("url", None),
                **fields,
            },
        })
    return documents


def _split_articles(text: str) -> list[tuple[str | None, str]]:
    """Tách văn bản luật thành (tiêu đề Điều, nội dung); phần mở đầu có tiêu đề None."""
    matches = list(_ARTICLE_HEADING.finditer(text))
    if not matches:
        return [(None, text)]
    sections = []
    if text[:matches[0].start()].strip():
        sections.append((None, text[:matches[0].start()]))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = match.group(1).strip().strip("*").strip()
        sections.append((heading, text[match.start():end]))
    return sections


def _splitter(chunk_size: int):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=min(CHUNK_OVERLAP, chunk_size // 4),
        separators=["\n\n", "\n", ". ", "; ", " ", ""],
        keep_separator="end",
    )


def _chunk_texts(document: dict, budget: int) -> list[tuple[str | None, str]]:
    """Cắt nội dung thành các đoạn dài tối đa ``budget`` ký tự."""
    content = document["content"]
    if document["metadata"].get("doc_type") != "legal":
        return [(None, text) for text in _splitter(budget).split_text(content)]

    pieces = []
    for heading, section in _split_articles(content):
        section = section.strip()
        if len(section) <= budget:
            pieces.append((heading, section))
            continue
        prefix = heading[:_ARTICLE_PREFIX_MAX] if heading else ""
        parts = _splitter(budget - len(prefix) - 1).split_text(section)
        for part_index, part in enumerate(parts):
            # Chunk đầu đã chứa sẵn dòng tiêu đề Điều.
            pieces.append((heading, f"{prefix}\n{part}" if prefix and part_index else part))
    return pieces


def chunk_documents(documents: list[dict]) -> list[dict]:
    """Chia Document thành chunks có id và chunk_index.

    Mỗi chunk bắt đầu bằng tên văn bản (vd "Thông tư 40/2021/TT-BTC ...") vì số
    hiệu chỉ xuất hiện ở header/trang đầu: thiếu dòng này thì chunk "Điều 7"
    không chứa số hiệu, BM25 không khớp được query theo số hiệu và dense cũng
    mất ngữ cảnh văn bản nào.
    """
    chunks = []
    for document in documents:
        doc_prefix = document["metadata"]["title"][:_TITLE_PREFIX_MAX]
        budget = CHUNK_SIZE - len(doc_prefix) - 1
        index = 0
        for heading, text in _chunk_texts(document, budget):
            text = text.strip()
            if not text:
                continue
            metadata = {**document["metadata"], "chunk_index": index}
            if heading:
                metadata["article"] = heading[:_ARTICLE_PREFIX_MAX]
            chunks.append({
                "id": f"{document['id']}::chunk-{index}",
                "content": f"{doc_prefix}\n{text}",
                "metadata": metadata,
            })
            index += 1
    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Thêm embedding vào từng chunk."""
    vectors = embed_texts([chunk["content"] for chunk in chunks])
    return [{**chunk, "embedding": vector} for chunk, vector in zip(chunks, vectors)]


def _to_chroma_metadata(metadata: dict) -> dict:
    # Chroma không nhận None; Task 5 khôi phục url=None khi đọc ra.
    return {key: value for key, value in metadata.items() if value is not None}


def index_to_vectorstore(chunks: list[dict]) -> None:
    """Upsert chunks vào ChromaDB và xoá chunk cũ của cùng document."""
    collection = get_collection()
    new_ids = {chunk["id"] for chunk in chunks}
    doc_prefixes = {chunk["id"].rsplit("::chunk-", 1)[0] + "::chunk-" for chunk in chunks}
    stale = [
        item_id for item_id in collection.get(include=[])["ids"]
        if item_id not in new_ids and item_id.startswith(tuple(doc_prefixes))
    ]
    if stale:
        collection.delete(ids=stale)

    for start in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch = chunks[start:start + UPSERT_BATCH_SIZE]
        collection.upsert(
            ids=[chunk["id"] for chunk in batch],
            documents=[chunk["content"] for chunk in batch],
            embeddings=[chunk["embedding"] for chunk in batch],
            metadatas=[_to_chroma_metadata(chunk["metadata"]) for chunk in batch],
        )


def load_indexed_chunks() -> list[dict]:
    """Đọc lại toàn bộ chunks đã index (corpus chung cho BM25 ở Task 6)."""
    response = get_collection().get(include=["documents", "metadatas"])
    chunks = [
        {"id": item_id, "content": content, "metadata": {"url": None, **metadata}}
        for item_id, content, metadata in zip(
            response["ids"], response["documents"], response["metadatas"]
        )
    ]
    return sorted(chunks, key=lambda chunk: (chunk["id"].rsplit("::chunk-", 1)[0],
                                             chunk["metadata"]["chunk_index"]))


def run_pipeline() -> None:
    """Chạy load, chunk, embed và index."""
    documents = load_documents()
    if not documents:
        raise SystemExit(f"Không có Markdown trong {STANDARDIZED_DIR}; chạy Task 3 trước.")
    chunks = chunk_documents(documents)
    embedded_chunks = embed_chunks(chunks)
    index_to_vectorstore(embedded_chunks)
    print(f"Indexed {len(embedded_chunks)} chunks from {len(documents)} documents "
          f"({EMBEDDING_PROVIDER}/{EMBEDDING_MODEL}, {CHUNKING_METHOD})")


if __name__ == "__main__":
    run_pipeline()
