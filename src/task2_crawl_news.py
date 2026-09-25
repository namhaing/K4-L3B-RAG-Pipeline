"""
Task 2 — Crawl bài viết/thông báo thực tế.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from crawl4ai import AsyncWebCrawler

DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "news"

# Danh sách URL bài viết cụ thể trên các báo điện tử uy tín
ARTICLE_URLS = [
    "https://baochinhphu.vn/chinh-sach-moi-co-hieu-luc-tu-thang-8-2021-102295627.htm",
    "https://baochinhphu.vn/huong-dan-dang-ky-kinh-doanh-102240101.htm",
    "https://baochinhphu.vn/chinh-sach-thue-102210601.htm",
    "https://congbao.chinhphu.vn/thu-tuc-dang-ky-doanh-nghiep-29837",
    "https://baochinhphu.vn/thu-tuong-chia-se-tam-nhin-phat-trien-kinh-te-va-bao-ve-moi-truong-bien-102240101.htm",
]


async def crawl_article(url: str) -> dict:
    """Crawl từng bài viết bằng Crawl4AI trực tiếp, không sử dụng fallback."""
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        if not result or not result.markdown or len(result.markdown.strip()) < 100:
            raise RuntimeError(f"Crawl failed or content too short for URL: {url}")
        
        return {
            "url": url,
            "title": result.metadata.get("title", "Bài viết hướng dẫn"),
            "date_crawled": datetime.now().isoformat(),
            "content_markdown": result.markdown,
        }


async def crawl_all() -> None:
    """Crawl và lưu từng bài thành một file JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for index, url in enumerate(ARTICLE_URLS, 1):
        try:
            article = await crawl_article(url)
            output = DATA_DIR / f"article_{index:02d}.json"
            output.write_text(
                json.dumps(article, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Saved article_{index:02d}.json from {url}")
        except Exception as error:
            print(f"Error crawling {url}: {error}")


if __name__ == "__main__":
    asyncio.run(crawl_all())
