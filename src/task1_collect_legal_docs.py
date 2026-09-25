"""
Task 1 — Thu thập tài liệu chính sách/quy định gốc từ nguồn .gov.vn.
"""

from pathlib import Path
import requests

DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"


def setup_directory() -> None:
    """Tạo thư mục lưu tài liệu gốc."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Ready: {DATA_DIR}")


# Danh sách URL tải trực tiếp file gốc từ .gov.vn
SOURCES = {
    "tt-40-2021-tt-btc-thue-ho-kinh-doanh.pdf": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2021/06/40-btc.pdf",
    "nd-01-2021-nd-cp-dang-ky-doanh-nghiep-hkd.pdf": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2021/01/01-cp.pdf",
    "nd-123-2020-nd-cp-hoa-don-chung-tu.pdf": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2020/10/123-cp.pdf",
}


def download_documents() -> None:
    """Tải và lưu tài liệu pháp luật gốc từ nguồn .gov.vn."""
    setup_directory()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for filename, direct_url in SOURCES.items():
        file_path = DATA_DIR / filename
        print(f"Downloading {filename} from {direct_url}...")
        try:
            response = requests.get(direct_url, headers=headers, timeout=30)
            response.raise_for_status()
            file_path.write_bytes(response.content)
            print(f"Successfully downloaded {filename} ({len(response.content)} bytes)")
        except Exception as e:
            print(f"Error downloading {filename} from {direct_url}: {e}")
            print(f"LƯU Ý: Nếu mạng chặn, hãy tải thủ công {filename} vào {DATA_DIR}")


if __name__ == "__main__":
    setup_directory()
    download_documents()
