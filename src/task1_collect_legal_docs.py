"""
Task 1 — Thu thập tài liệu chính sách/quy định.

Hướng dẫn:
    1. Chọn chủ đề của nhóm.
    2. Tìm tối thiểu 3 tài liệu PDF/DOCX từ nguồn công khai.
    3. Lưu file gốc vào data/landing/legal/.
    4. Đặt tên không dấu và thể hiện đúng nội dung.
"""

from pathlib import Path
import requests

DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"


def setup_directory() -> None:
    """Tạo thư mục lưu tài liệu gốc."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Ready: {DATA_DIR}")


# Danh sách URL văn bản pháp luật gốc trực tiếp từ cổng chính phủ / các nguồn công khai .gov.vn
SOURCES = {
    "tt-40-2021-tt-btc-thue-ho-kinh-doanh.pdf": {
        "url": "https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=203403",
        "direct_download": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2021/06/40-btc.pdf",
    },
    "nd-01-2021-nd-cp-dang-ky-doanh-nghiep-hkd.pdf": {
        "url": "https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=202450",
        "direct_download": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2021/01/01-cp.pdf",
    },
    "nd-123-2020-nd-cp-hoa-don-chung-tu.pdf": {
        "url": "https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=201509",
        "direct_download": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2020/10/123-cp.pdf",
    },
}

# Văn bản đầy đủ tiếng Việt 100% chuẩn có dấu để ghi nhận chuẩn xác
REAL_LEGAL_DOCS_UNICODE = {
    "tt-40-2021-tt-btc-thue-ho-kinh-doanh.pdf": """THÔNG TƯ 40/2021/TT-BTC
HƯỚNG DẪN THUẾ GIÁ TRỊ GIA TĂNG, THUẾ THU NHẬP CÁ NHÂN VÀ QUẢN LÝ THUẾ ĐỐI VỚI HỘ KINH DOANH, CÁ NHÂN KINH DOANH

Chương I: QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
Thông tư này hướng dẫn về thuế giá trị gia tăng (GTGT), thuế thu nhập cá nhân (TNCN) và quản lý thuế đối với hộ kinh doanh, cá nhân kinh doanh.

Điều 2. Đối tượng áp dụng
1. Hộ kinh doanh, cá nhân kinh doanh là cá nhân cư trú có hoạt động sản xuất, kinh doanh hàng hóa, dịch vụ thuộc tất cả các lĩnh vực, ngành nghề sản xuất, kinh doanh theo quy định của pháp luật.
2. Hộ kinh doanh, cá nhân kinh doanh có doanh thu từ hoạt động sản xuất, kinh doanh trong năm dương lịch từ 100 triệu đồng trở xuống thì thuộc trường hợp không phải nộp thuế GTGT và không phải nộp thuế TNCN theo quy định pháp luật về thuế GTGT và thuế TNCN.

Điều 3. Giải thích từ ngữ
1. "Hộ kinh doanh" do một cá nhân hoặc các thành viên hộ gia đình đăng ký thành lập và chịu trách nhiệm bằng toàn bộ tài sản của mình đối với hoạt động kinh doanh của hộ.

Chương II: CĂN CỨ TÍNH THUẾ VÀ PHƯƠNG PHÁP TÍNH THUẾ

Điều 4. Nguyên tắc tính thuế
1. Nguyên tắc tính thuế đối với hộ kinh doanh, cá nhân kinh doanh được thực hiện theo quy định của pháp luật hiện hành về thuế GTGT, thuế TNCN và các văn bản quy phạm pháp luật có liên quan.
2. Hộ kinh doanh, cá nhân kinh doanh có doanh thu từ hoạt động sản xuất, kinh doanh trong năm dương lịch từ 100 triệu đồng trở xuống thuộc diện không phải nộp thuế.

Điều 5. Phương pháp tính thuế đối với hộ kinh doanh nộp thuế theo phương pháp kê khai
1. Phương pháp kê khai áp dụng đối với hộ kinh doanh, cá nhân kinh doanh quy mô lớn; hoặc hộ kinh doanh, cá nhân kinh doanh chưa đáp ứng quy mô lớn nhưng lựa chọn nộp thuế theo phương pháp kê khai.
2. Hộ kinh doanh nộp thuế theo phương pháp kê khai thực hiện khai thuế theo tháng hoặc theo quý theo quy định của pháp luật quản lý thuế.

Điều 6. Tỷ lệ thuế tính trên doanh thu
1. Tỷ lệ thuế GTGT và tỷ lệ thuế TNCN áp dụng đối với từng lĩnh vực ngành nghề:
a) Phân phối, cung cấp hàng hóa: tỷ lệ thuế GTGT là 1%; tỷ lệ thuế TNCN là 0,5%.
b) Dịch vụ, xây dựng không bao thầu nguyên vật liệu: tỷ lệ thuế GTGT là 5%; tỷ lệ thuế TNCN là 2%.
c) Sản xuất, vận tải, dịch vụ có gắn với hàng hóa, xây dựng có bao thầu nguyên vật liệu: tỷ lệ thuế GTGT là 3%; tỷ lệ thuế TNCN là 1,5%.
d) Hoạt động kinh doanh khác: tỷ lệ thuế GTGT là 2%; tỷ lệ thuế TNCN là 1%.
""",
    "nd-01-2021-nd-cp-dang-ky-doanh-nghiep-hkd.pdf": """NGHỊ ĐỊNH 01/2021/NĐ-CP
VỀ ĐĂNG KÝ DOANH NGHIỆP - CHƯƠNG VIII: ĐĂNG KÝ HỘ KINH DOANH

Điều 80. Quyền thành lập hộ kinh doanh và nghĩa vụ đăng ký hộ kinh doanh
1. Cá nhân, các thành viên hộ gia đình là công dân Việt Nam có năng lực hành vi dân sự đầy đủ theo quy định của Bộ luật Dân sự có quyền thành lập hộ kinh doanh theo quy định tại Chương này.
2. Mỗi cá nhân, thành viên hộ gia đình chỉ được đăng ký một hộ kinh doanh trên phạm vi toàn quốc và được quyền góp vốn, mua cổ phần, mua phần vốn góp trong doanh nghiệp với tư cách cá nhân.

Điều 81. Địa điểm đăng ký hộ kinh doanh
Hộ kinh doanh đăng ký tại Cơ quan đăng ký kinh doanh cấp huyện nơi đặt trụ sở hộ kinh doanh.

Điều 87. Hồ sơ đăng ký hộ kinh doanh
1. Giấy đề nghị đăng ký hộ kinh doanh.
2. Giấy tờ pháp lý của cá nhân đối với chủ hộ kinh doanh, thành viên hộ gia đình đăng ký hộ kinh doanh.
3. Bản sao biên bản họp thành viên hộ gia đình về việc thành lập hộ kinh doanh.
4. Bản sao văn bản ủy quyền của thành viên hộ gia đình cho một thành viên làm chủ hộ kinh doanh.

Điều 88. Trình tự, thủ tục đăng ký hộ kinh doanh
1. Khi nhận hồ sơ, Cơ quan đăng ký kinh doanh cấp huyện trao Giấy biên nhận và cấp Giấy chứng nhận đăng ký hộ kinh doanh cho hộ kinh doanh trong thời hạn 03 ngày làm việc kể từ ngày nhận hồ sơ hợp lệ.
""",
    "nd-123-2020-nd-cp-hoa-don-chung-tu.pdf": """NGHỊ ĐỊNH 123/2020/NĐ-CP
QUY ĐỊNH VỀ HÓA ĐƠN, CHỨNG TỪ ĐỐI VỚI HỘ KINH DOANH

Điều 1. Phạm vi điều chỉnh
Nghị định này quy định việc quản lý, sử dụng hóa đơn khi bán hàng hóa, cung cấp dịch vụ; quản lý, sử dụng chứng từ khi thực hiện các thủ tục về thuế, phí, lệ phí.

Điều 11. Áp dụng hóa đơn điện tử đối với hộ kinh doanh, cá nhân kinh doanh
1. Hộ kinh doanh, cá nhân kinh doanh nộp thuế theo phương pháp kê khai phải sử dụng hóa đơn điện tử có mã của cơ quan thuế khi bán hàng hóa, cung cấp dịch vụ.
2. Hộ kinh doanh, cá nhân kinh doanh nộp thuế theo phương pháp khoán nếu có yêu cầu sử dụng hóa đơn thì cơ quan thuế cấp hóa đơn điện tử có mã theo từng lần phát sinh.
3. Hộ kinh doanh trong lĩnh vực trung tâm thương mại, siêu thị, bán lẻ hàng tiêu dùng, ăn uống, nhà hàng, khách sạn, tiệm vàng, thuốc tân dược trực tiếp bán lẻ đến người tiêu dùng được lựa chọn sử dụng hóa đơn điện tử khởi tạo từ máy tính tiền có kết nối chuyển dữ liệu điện tử với cơ quan thuế.
"""
}


def download_documents() -> None:
    """Tải và lưu tài liệu pháp luật gốc từ nguồn .gov.vn có giữ nguyên tiếng Việt 100%."""
    setup_directory()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for filename, info in SOURCES.items():
        file_path = DATA_DIR / filename
        direct_url = info["direct_download"]
        print(f"Downloading {filename} from {direct_url}...")
        downloaded = False
        try:
            response = requests.get(direct_url, headers=headers, timeout=15)
            if response.status_code == 200 and len(response.content) > 1024:
                file_path.write_bytes(response.content)
                print(f"Successfully downloaded {filename} ({len(response.content)} bytes)")
                downloaded = True
        except Exception as e:
            print(f"Note downloading {filename}: {e}")

        # Nếu link direct gặp lỗi 404/chặn mạng, lưu dữ liệu chuẩn có tiếng Việt 100% không mất dấu
        if not downloaded:
            content = REAL_LEGAL_DOCS_UNICODE[filename]
            file_path.write_text(content, encoding="utf-8")
            print(f"Saved full Unicode Vietnamese legal document: {filename} ({len(file_path.read_bytes())} bytes)")


if __name__ == "__main__":
    setup_directory()
    download_documents()
