"""
Task 2 — Crawl bài viết hướng dẫn về hộ kinh doanh.

Mỗi URL là một bài viết cụ thể (không phải trang chủ/danh mục). Chỉ lấy phần
thân bài theo CSS selector của từng báo để loại menu, quảng cáo, bài liên quan.
Bài nào crawl lỗi hoặc quá ngắn thì báo lỗi, không ghi nội dung thay thế.

Các bài được chọn cùng giai đoạn với văn bản pháp luật trong corpus (2022–2025).
"""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify


DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "news"

ARTICLE_URLS = [
    "https://baochinhphu.vn/ho-so-thu-tuc-dang-ky-ho-kinh-doanh-nhu-the-nao-102230906140208218.htm",
    "https://tuoitre.vn/dang-ky-kinh-doanh-cho-gia-dinh-gom-nhung-thu-tuc-gi-20230406100955234.htm",
    "https://baochinhphu.vn/ho-kinh-doanh-phai-nop-cac-loai-thue-phi-nao-102220722151801844.htm",
    "https://baochinhphu.vn/dieu-kien-ho-kinh-doanh-nop-thue-theo-phuong-phap-ke-khai-102230620094419843.htm",
    "https://baochinhphu.vn/ho-kinh-doanh-co-the-lua-chon-phuong-phap-nop-thue-102231030145643482.htm",
    "https://dansinh.dantri.com.vn/tien-luong-tien-cong/huong-dan-nguoi-ban-hang-online-tinh-cac-loai-thue-phi-phai-nop-20241003104726709.htm",
    "https://vnexpress.net/luu-y-khi-ho-kinh-doanh-su-dung-hoa-don-dien-tu-tu-may-tinh-tien-4944139.html",
]

# domain -> (selector sapo/lead, selector thân bài)
SITE_SELECTORS = {
    "baochinhphu.vn": ("h2.detail-sapo", "div.detail-content"),
    "tuoitre.vn": ("h2.detail-sapo", "div.detail-content"),
    "dansinh.dantri.com.vn": ("h2.singular-sapo, div.singular-sapo", "div.content"),
    "vnexpress.net": ("p.description", "article.fck_detail"),
}
# Khối không thuộc nội dung bài (box liên quan, ảnh, quảng cáo...).
NOISE_SELECTORS = "script, style, figure, table.picture, h1, [type='RelatedNewsBox'], .kbwscwl-relatedbox, " \
                  ".box-tinlienquanv2, .related, .ads, .banner, iframe, video"

MIN_CONTENT_CHARS = 800
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name}) \
            or soup.find("meta", attrs={"itemprop": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def crawl_article(url: str) -> dict:
    """Tải một bài và trích thân bài thành Markdown."""
    domain = urlparse(url).netloc.removeprefix("www.")
    if domain not in SITE_SELECTORS:
        raise ValueError(f"Chưa có selector cho {domain}")
    sapo_selector, body_selector = SITE_SELECTORS[domain]

    response = None
    for _ in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            break
        except requests.ConnectionError:
            continue
    if response is None:
        raise ConnectionError("không kết nối được sau 3 lần thử")
    response.raise_for_status()
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    body = soup.select_one(body_selector)
    if body is None:
        raise ValueError(f"Không tìm thấy thân bài ({body_selector})")
    for noise in body.select(NOISE_SELECTORS):
        noise.decompose()

    title = _meta(soup, "og:title") or (soup.title.string if soup.title else "")
    title = re.sub(r"\s*[-|]\s*(Báo VnExpress.*|Tuổi Trẻ Online|Báo Dân trí)$", "", title).strip()
    body_md = markdownify(str(body), heading_style="ATX", strip=["a", "img"])
    sapo = soup.select_one(sapo_selector)
    sapo_text = sapo.get_text(" ", strip=True) if sapo else ""
    # Một số báo (vnexpress) đã có sẵn sapo trong thân bài.
    parts = [sapo_text] if sapo_text and sapo_text[:80] not in body_md else []
    parts.append(body_md)
    content = re.sub(r"\n{3,}", "\n\n", "\n\n".join(parts)).strip()

    if len(content) < MIN_CONTENT_CHARS:
        raise ValueError(f"Nội dung quá ngắn ({len(content)} ký tự)")
    if re.search(r"\b404\b|not found", title, re.IGNORECASE):
        raise ValueError(f"Trang lỗi: {title}")

    return {
        "url": url,
        "title": title,
        "published_date": _meta(soup, "article:published_time", "datePublished", "pubdate"),
        "date_crawled": datetime.now().isoformat(timespec="seconds"),
        "content_markdown": content,
    }


def crawl_all() -> None:
    """Crawl và lưu từng bài thành một file JSON; xoá JSON cũ không còn trong danh sách."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    expected = {f"article_{index:02d}.json" for index in range(1, len(ARTICLE_URLS) + 1)}
    for stale in DATA_DIR.glob("article_*.json"):
        if stale.name not in expected:
            stale.unlink()
            print(f"Removed stale: {stale.name}")

    for index, url in enumerate(ARTICLE_URLS, 1):
        output = DATA_DIR / f"article_{index:02d}.json"
        try:
            article = crawl_article(url)
            output.write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Saved {output.name} ({len(article['content_markdown']):,} chars): {article['title']}")
        except Exception as error:
            # Không giữ lại file cũ của vị trí này: nó thuộc URL/lần crawl khác.
            output.unlink(missing_ok=True)
            print(f"FAILED {url}: {error}")


if __name__ == "__main__":
    crawl_all()
