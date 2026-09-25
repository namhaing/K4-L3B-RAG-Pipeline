import html
import logging
import re
import time

import streamlit as st
from dotenv import load_dotenv


load_dotenv()

from src.task10_generation import (  # noqa: E402  (cần load .env trước khi import)
    DISCLAIMER,
    REFUSAL_MESSAGE,
    TOP_K,
    _generate,
    extract_citations,
)


logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Hỏi luật hộ kinh doanh",
    page_icon="⚖️",
    layout="centered",
    initial_sidebar_state="auto",
)

ASSISTANT_AVATAR = ":material/balance:"
USER_AVATAR = ":material/storefront:"

TOPICS = [
    ("Đăng ký hộ kinh doanh", "Hồ sơ đăng ký hộ kinh doanh gồm những gì và nộp ở đâu?"),
    ("Thuế", "Doanh thu bao nhiêu một năm thì hộ kinh doanh phải nộp thuế?"),
    ("Hoá đơn điện tử", "Hộ kinh doanh nào phải dùng hoá đơn điện tử khởi tạo từ máy tính tiền?"),
    ("Bán hàng online", "Bán hàng trên sàn thương mại điện tử thì ai khấu trừ và nộp thuế thay?"),
]

SAMPLE_QUESTIONS = [
    "Nghị định 123/2020/NĐ-CP quy định gì về hoá đơn?",
    "Tỷ lệ thuế GTGT và TNCN với quán ăn là bao nhiêu?",
    "Bán hàng qua Facebook có phải đăng ký hộ kinh doanh không?",
    "Thủ tục ly hôn thuận tình gồm những bước nào?",
]

METHOD_LABELS = {
    "hybrid": "Kết hợp ngữ nghĩa và từ khoá",
    "pageindex": "Tra theo mục lục văn bản (PageIndex)",
    "none": "Không đủ căn cứ",
}

SCORE_LABELS = {"dense": "cosine", "bm25": "BM25", "hybrid": "RRF", "pageindex": "PageIndex"}

CITATION_PATTERN = re.compile(r"\[Document\s+(\d+)\]", re.IGNORECASE)
ARTICLE_PATTERN = re.compile(r"((?:Điều|Khoản|Điểm)\s+\d+[a-zđ]?)")
EXCERPT_CHARS = 700


STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&family=Noto+Serif:ital,wght@0,400;0,600;1,400&display=swap');

:root {
    --ink: #1C2536;
    --ink-soft: #56607A;
    --signature: #1F3A93;
    --seal: #B3261E;
    --seal-wash: rgba(179, 38, 30, 0.07);
    --rule: #DCE0E8;
    --desk: #F2F4F7;
    --marker: #FFF0A6;
}

/* Tiêu đề trang: khối đầu văn bản, gạch ngắn màu dấu đỏ bên dưới */
.masthead { margin: 0.5rem 0 2rem; }
.masthead h1 {
    font-size: 2.35rem;
    line-height: 1.15;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0;
    padding: 0;
}
.masthead .rule {
    width: 3.5rem;
    height: 3px;
    background: var(--seal);
    margin: 0.9rem 0 1rem;
    border-radius: 2px;
}
.masthead p {
    color: var(--ink-soft);
    font-size: 1.02rem;
    line-height: 1.6;
    max-width: 36rem;
    margin: 0;
}

.topic-name {
    color: var(--ink-soft);
    font-size: 0.82rem;
    font-weight: 600;
    margin: 0.6rem 0 0.3rem;
}

/* Nút câu hỏi: như một tờ phiếu, căn trái, viền mực xanh bên trái */
.stButton > button[kind="secondary"] {
    justify-content: flex-start;
    text-align: left;
    width: 100%;
    min-height: 3.4rem;
    background: #FFFFFF;
    border: 1px solid var(--rule);
    border-left: 3px solid var(--signature);
    color: var(--ink);
    line-height: 1.45;
    padding: 0.6rem 0.85rem;
    transition: border-color 120ms ease, background 120ms ease;
}
.stButton > button p {
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
    text-align: left;
}
.stButton > button div { overflow: visible; }
.stButton > button[kind="secondary"]:hover {
    border-color: var(--signature);
    background: #F7F9FD;
    color: var(--signature);
}
.stButton > button:focus-visible {
    outline: 2px solid var(--signature);
    outline-offset: 2px;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"] { min-height: 0; font-size: 0.9rem; }

/* Hội thoại */
[data-testid="stChatMessage"] { background: transparent; padding: 0.9rem 0; }
[data-testid="stChatMessageContent"] p,
[data-testid="stChatMessageContent"] li { line-height: 1.7; }

/* Con dấu trích dẫn: vòng tròn đỏ viền kép, hơi nghiêng như dấu đóng tay */
.seal {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.45em;
    height: 1.45em;
    margin: 0 0.15em;
    border: 1.5px solid var(--seal);
    border-radius: 50%;
    box-shadow: inset 0 0 0 1.5px #FFFFFF, inset 0 0 0 2.5px rgba(179, 38, 30, 0.45);
    background: var(--seal-wash);
    color: var(--seal);
    font-size: 0.78em;
    font-weight: 700;
    line-height: 1;
    vertical-align: 0.12em;
    transform: rotate(-9deg);
    cursor: help;
}
.seal.muted {
    border-color: #A7AEBD;
    box-shadow: inset 0 0 0 1.5px #FFFFFF, inset 0 0 0 2.5px rgba(86, 96, 122, 0.3);
    background: transparent;
    color: var(--ink-soft);
    cursor: default;
}

.meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.75rem 0 0.4rem;
}
.chip {
    font-size: 0.78rem;
    color: var(--ink-soft);
    background: var(--desk);
    border-radius: 999px;
    padding: 0.2rem 0.65rem;
}
.chip.warn { color: var(--seal); background: var(--seal-wash); }

.refusal {
    border: 1px dashed #A7AEBD;
    border-radius: 0.5rem;
    padding: 0.9rem 1rem;
    color: var(--ink);
    line-height: 1.6;
}
.refusal small { display: block; color: var(--ink-soft); margin-top: 0.35rem; }

/* Phiếu nguồn: trích đoạn văn bản bằng chữ có chân như công văn */
.slip {
    border-top: 1px solid var(--rule);
    padding: 0.9rem 0 0.4rem;
}
.slip:first-child { border-top: none; padding-top: 0.2rem; }
.slip-head { display: flex; gap: 0.7rem; align-items: flex-start; }
.slip-head .seal { flex: none; font-size: 0.95rem; margin: 0.1rem 0 0; }
.slip-title { font-weight: 600; color: var(--ink); line-height: 1.4; }
.slip-meta { color: var(--ink-soft); font-size: 0.82rem; margin-top: 0.15rem; line-height: 1.5; }
.slip-meta .cited { color: var(--seal); font-weight: 600; }
.slip-quote {
    font-family: 'Noto Serif', Georgia, serif;
    font-size: 0.9rem;
    line-height: 1.75;
    color: #2E3850;
    margin: 0.6rem 0 0.4rem 2.2rem;
    padding-left: 0.85rem;
    border-left: 2px solid var(--rule);
    max-width: 38rem;
}
.slip-quote mark { background: var(--marker); color: inherit; padding: 0 0.1em; border-radius: 2px; }
.slip-link { margin-left: 2.2rem; font-size: 0.82rem; }

.disclaimer {
    font-size: 0.8rem;
    line-height: 1.55;
    color: var(--ink-soft);
    border-left: 3px solid var(--seal);
    padding: 0.35rem 0 0.35rem 0.75rem;
}

@media (max-width: 640px) {
    .masthead h1 { font-size: 1.8rem; }
    .slip-quote, .slip-link { margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) {
    .stButton > button { transition: none; }
}
</style>
"""


def ask(question: str) -> None:
    st.session_state.pending_query = question


def clear_chat() -> None:
    st.session_state.messages = []


def safe_url(url: object) -> str | None:
    return url if isinstance(url, str) and url.startswith(("http://", "https://")) else None


def score_text(source: dict) -> str:
    method = source.get("retrieval_method", "")
    return f"{SCORE_LABELS.get(method, method)} {float(source.get('score', 0.0)):.3f}"


def render_answer(answer: str, sources: list[dict]) -> str:
    """Escape câu trả lời của LLM rồi đổi [Document n] thành con dấu có tooltip."""
    text = html.escape(answer, quote=False)

    def seal(match: re.Match) -> str:
        n = int(match.group(1))
        if not 1 <= n <= len(sources):
            return ""
        title = html.escape(sources[n - 1]["metadata"].get("title", ""))
        return f'<span class="seal" title="Nguồn {n}: {title}">{n}</span>'

    return CITATION_PATTERN.sub(seal, text)


def render_excerpt(content: str) -> str:
    excerpt = content.strip()
    if len(excerpt) > EXCERPT_CHARS:
        excerpt = excerpt[:EXCERPT_CHARS].rsplit(" ", 1)[0] + " …"
    excerpt = html.escape(excerpt)
    excerpt = ARTICLE_PATTERN.sub(r"<mark>\1</mark>", excerpt)
    return excerpt.replace("\n", "<br>")


def render_sources(sources: list[dict], cited: set[int]) -> str:
    slips = []
    for n, source in enumerate(sources, 1):
        metadata = source.get("metadata", {})
        is_cited = n in cited
        details = [
            metadata.get("doc_number"),
            metadata.get("article"),
            "Văn bản pháp luật" if metadata.get("doc_type") == "legal" else "Bài viết hướng dẫn",
            score_text(source),
        ]
        meta = ", ".join(html.escape(str(item)) for item in details if item)
        if is_cited:
            meta = f'<span class="cited">Được trích dẫn</span>, {meta}'
        url = safe_url(metadata.get("url"))
        link = (
            f'<div class="slip-link"><a href="{html.escape(url)}" target="_blank" '
            f'rel="noopener">Mở văn bản gốc</a></div>'
            if url
            else f'<div class="slip-link slip-meta">Tệp: {html.escape(metadata.get("source", ""))}</div>'
        )
        slips.append(
            f'<div class="slip">'
            f'<div class="slip-head"><span class="seal{"" if is_cited else " muted"}">{n}</span>'
            f'<div><div class="slip-title">{html.escape(metadata.get("title", "Không rõ tiêu đề"))}</div>'
            f'<div class="slip-meta">{meta}</div></div></div>'
            f'<div class="slip-quote">{render_excerpt(source.get("content", ""))}</div>'
            f"{link}</div>"
        )
    return "".join(slips)


def render_assistant_message(message: dict) -> None:
    sources = message.get("sources", [])
    retrieval_source = message.get("retrieval_source", "none")

    if retrieval_source == "none" or not sources:
        body = html.escape(message["content"])
        hint = "Hãy hỏi cụ thể hơn, ví dụ nêu ngành nghề, số hiệu văn bản hoặc thủ tục cần làm."
        if message.get("error"):
            hint = message["error"]
        st.markdown(
            f'<div class="refusal">{body}<small>{html.escape(hint)}</small></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(render_answer(message["content"], sources), unsafe_allow_html=True)

    cited = set(extract_citations(message["content"]))
    chips = [
        f'<span class="chip{" warn" if retrieval_source == "none" else ""}">'
        f"{METHOD_LABELS.get(retrieval_source, retrieval_source)}</span>"
    ]
    if sources:
        chips.append(f'<span class="chip">{len(cited)}/{len(sources)} nguồn được trích dẫn</span>')
    if message.get("latency") is not None:
        chips.append(f'<span class="chip">{message["latency"]:.1f} giây</span>')
    st.markdown(f'<div class="meta-row">{"".join(chips)}</div>', unsafe_allow_html=True)

    if sources:
        with st.expander(f"Xem {len(sources)} đoạn văn bản đã dùng", icon=":material/description:"):
            st.markdown(render_sources(sources, cited), unsafe_allow_html=True)


def answer_query(query: str, top_k: int, use_hybrid: bool) -> dict:
    start = time.perf_counter()
    try:
        result = _generate(query, top_k=top_k, use_reranking=use_hybrid)
        error = None
    except Exception:
        logger.exception("Generation failed")
        result = {"answer": REFUSAL_MESSAGE, "sources": [], "retrieval_source": "none"}
        error = "Hệ thống tra cứu đang gặp lỗi. Kiểm tra cấu hình .env và chỉ mục ChromaDB rồi thử lại."
    return {
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
        "retrieval_source": result["retrieval_source"],
        "latency": time.perf_counter() - start,
        "error": error,
    }


st.markdown(STYLE, unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.markdown("### Hỏi luật hộ kinh doanh")
    st.caption(
        "Trả lời từ văn bản pháp luật và bài hướng dẫn chính thống về đăng ký, "
        "thuế, hoá đơn điện tử và bán hàng qua sàn thương mại điện tử."
    )

    st.markdown("**Câu hỏi mẫu**")
    for index, question in enumerate(SAMPLE_QUESTIONS):
        st.button(question, key=f"sample-{index}", on_click=ask, args=(question,))

    st.markdown("**Tuỳ chỉnh tra cứu**")
    top_k = st.slider(
        "Số đoạn văn bản tham khảo",
        min_value=3,
        max_value=10,
        value=TOP_K,
        help="Nhiều đoạn hơn giúp đủ căn cứ nhưng câu trả lời chậm hơn.",
    )
    mode = st.radio(
        "Cách tìm nguồn",
        ["Kết hợp ngữ nghĩa và từ khoá", "Chỉ theo ngữ nghĩa"],
        help="Kết hợp (dense + BM25 + RRF) bắt tốt câu hỏi có số hiệu văn bản như 40/2021/TT-BTC.",
    )
    use_hybrid = mode == "Kết hợp ngữ nghĩa và từ khoá"

    if st.session_state.messages:
        st.button("Xoá cuộc trò chuyện", on_click=clear_chat, icon=":material/delete:", type="tertiary")

    st.markdown(f'<div class="disclaimer">{DISCLAIMER} Với trường hợp cụ thể, '
                "hãy liên hệ cơ quan thuế hoặc phòng đăng ký kinh doanh nơi bạn cư trú.</div>",
                unsafe_allow_html=True)

st.markdown(
    """
    <div class="masthead">
        <h1>Hỏi luật cho hộ kinh doanh</h1>
        <div class="rule"></div>
        <p>Hỏi về đăng ký, thuế, hoá đơn điện tử hay bán hàng online.
        Mỗi câu trả lời đều dẫn về văn bản và Điều khoản cụ thể để bạn tự kiểm tra.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not st.session_state.messages:
    columns = st.columns(2, gap="medium")
    for index, (topic, question) in enumerate(TOPICS):
        with columns[index % 2]:
            st.markdown(f'<div class="topic-name">{topic}</div>', unsafe_allow_html=True)
            st.button(question, key=f"topic-{index}", on_click=ask, args=(question,))

for message in st.session_state.messages:
    if message["role"] == "user":
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(message["content"])
    else:
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            render_assistant_message(message)

query = st.chat_input("Ví dụ: Quán ăn doanh thu 500 triệu một năm nộp thuế bao nhiêu?")
if not query:
    query = st.session_state.pop("pending_query", None)

if query and query.strip():
    query = query.strip()
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(query)

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        with st.spinner("Đang tra văn bản…"):
            reply = answer_query(query, top_k, use_hybrid)
        render_assistant_message(reply)
    st.session_state.messages.append(reply)
    # Chạy lại để ẩn khung chủ đề gợi ý và hiện nút xoá ở sidebar.
    st.rerun()
