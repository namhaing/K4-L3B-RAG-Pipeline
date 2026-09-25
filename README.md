# Chatbot RAG — Pháp luật cho hộ kinh doanh

Chatbot trả lời câu hỏi về pháp luật dành cho **hộ kinh doanh cá thể**: đăng ký hộ kinh doanh, thuế GTGT/TNCN, phương pháp khoán và kê khai, hóa đơn điện tử, bán hàng online. Mỗi câu trả lời có citation tới văn bản luật hoặc bài viết làm nguồn. Chatbot từ chối khi câu hỏi nằm ngoài phạm vi hoặc không đủ căn cứ.

> ⚠️ **Phiên bản corpus: quy định giai đoạn 2021–2025.** Từ 01/01/2026 chính sách thuế hộ kinh doanh đã thay đổi (ngưỡng miễn thuế tăng, bỏ thuế khoán) và NĐ 01/2021/NĐ-CP đã hết hiệu lực từ 01/07/2025. Câu trả lời chỉ mang tính tham khảo, không thay thế tư vấn pháp lý.

Nhóm Khê:
- **Nguyễn Hải Nam** (Leader): chunking, embedding, ChromaDB, dense, BM25, RRF, calibrate threshold (Task 4–7)
- **Lê Trung Kiên**: thu thập và chuẩn hoá dữ liệu, PageIndex fallback (Task 1–3, 8)
- **Bùi Phương Duy**: retrieval pipeline, generation, chatbot, evaluation (Task 9–10, `app.py`, `RESULT.md`)

## Kiến trúc

```
Task 1–3  PDF Công báo + bài báo  →  Markdown chuẩn hoá (header: title, Source, Số hiệu, Hiệu lực)
Task 4    chunk theo Chương → Điều → recursive (800/100)  →  embed text-embedding-3-small  →  ChromaDB (cosine)
Task 5    dense search (score = cosine gốc) ─┐
Task 6    BM25 (giữ số hiệu văn bản)        ─┴→  Task 7  RRF (k=60, fuse một lần)
Task 9    best dense < SCORE_THRESHOLD  →  Task 8  PageIndex (vectorless, cây mục lục); lỗi/hết giờ → hybrid
Task 10   reorder + format context  →  LLM (gpt-4o-mini)  →  answer + citation [Document n], hoặc safe refusal
app.py    Streamlit: nguồn, score, retrieval method, highlight câu được trích, conversation memory
```

## Dữ liệu

### Văn bản pháp luật (`data/landing/legal/`)

Bản đăng Công báo (PDF có lớp text). Bản "signed" trên vanban.chinhphu.vn là PDF scan không trích xuất được text.

| File | Văn bản | Số hiệu | Ngày ban hành | Tình trạng hiệu lực | Nguồn |
|---|---|---|---|---|---|
| `tt-40-2021-tt-btc-thue-ho-kinh-doanh.pdf` | Thông tư hướng dẫn thuế GTGT, TNCN và quản lý thuế đối với hộ kinh doanh, cá nhân kinh doanh | 40/2021/TT-BTC | 01/06/2021 | Hiệu lực từ 01/08/2021; sửa đổi bởi TT 100/2021/TT-BTC; chính sách thay đổi từ 01/01/2026 | [Công báo số 649+650](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/6/33850/36037-1-2021649-65040-2021-tt-btc.pdf) |
| `nd-01-2021-nd-cp-dang-ky-doanh-nghiep-hkd.pdf` | Nghị định về đăng ký doanh nghiệp (Chương VIII: hộ kinh doanh) | 01/2021/NĐ-CP | 04/01/2021 | Hiệu lực từ 04/01/2021; **hết hiệu lực từ 01/07/2025** | [Công báo số 113+114](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/1/32981/34281-1-2021113-11401-2021-nd-cp.pdf) |
| `nd-123-2020-nd-cp-hoa-don-chung-tu.pdf` | Nghị định quy định về hóa đơn, chứng từ (61 Điều, không gồm phụ lục mẫu biểu) | 123/2020/NĐ-CP | 19/10/2020 | Hiệu lực từ 01/07/2022; sửa đổi bởi NĐ 70/2025/NĐ-CP | [Công báo số 1011+1012](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2020/10/32290/32999-1-20201011-1012123-2020-nd-cp.pdf) |

### Bài viết (`data/landing/news/`)

Chỉ lấy phần thân bài (bỏ menu, box bài liên quan, quảng cáo).

| File | Tiêu đề | Báo | Ngày đăng |
|---|---|---|---|
| `article_01.json` | [Hồ sơ, thủ tục đăng ký hộ kinh doanh như thế nào?](https://baochinhphu.vn/ho-so-thu-tuc-dang-ky-ho-kinh-doanh-nhu-the-nao-102230906140208218.htm) | baochinhphu.vn | 07/09/2023 |
| `article_02.json` | [Đăng ký kinh doanh cho gia đình gồm những thủ tục gì?](https://tuoitre.vn/dang-ky-kinh-doanh-cho-gia-dinh-gom-nhung-thu-tuc-gi-20230406100955234.htm) | tuoitre.vn | 07/04/2023 |
| `article_03.json` | [Hộ kinh doanh phải nộp các loại thuế, phí nào?](https://baochinhphu.vn/ho-kinh-doanh-phai-nop-cac-loai-thue-phi-nao-102220722151801844.htm) | baochinhphu.vn | 23/07/2022 |
| `article_04.json` | [Điều kiện hộ kinh doanh nộp thuế theo phương pháp kê khai](https://baochinhphu.vn/dieu-kien-ho-kinh-doanh-nop-thue-theo-phuong-phap-ke-khai-102230620094419843.htm) | baochinhphu.vn | 22/06/2023 |
| `article_05.json` | [Hộ kinh doanh có thể lựa chọn phương pháp nộp thuế?](https://baochinhphu.vn/ho-kinh-doanh-co-the-lua-chon-phuong-phap-nop-thue-102231030145643482.htm) | baochinhphu.vn | 31/10/2023 |
| `article_06.json` | [Hướng dẫn người bán hàng online tính các loại thuế phí phải nộp](https://dansinh.dantri.com.vn/tien-luong-tien-cong/huong-dan-nguoi-ban-hang-online-tinh-cac-loai-thue-phi-phai-nop-20241003104726709.htm) | dansinh.dantri.com.vn | 03/10/2024 |
| `article_07.json` | [Lưu ý khi hộ kinh doanh sử dụng hóa đơn điện tử từ máy tính tiền](https://vnexpress.net/luu-y-khi-ho-kinh-doanh-su-dung-hoa-don-dien-tu-tu-may-tinh-tien-4944139.html) | vnexpress.net | 26/09/2025 |

Ngày thu thập: 25/09/2026. Golden dataset: 16 câu trong [group_project/evaluation/golden_dataset.json](group_project/evaluation/golden_dataset.json); mọi `expected_context` là đoạn nguyên văn trong corpus.

## Cài đặt

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
cp .env.example .env            # Windows: copy .env.example .env
```

Điền vào `.env` (không commit file này):

| Biến | Giá trị | Ghi chú |
|---|---|---|
| `OPENAI_API_KEY` | key OpenAI | Dùng cho cả embedding và LLM |
| `LLM_PROVIDER` / `LLM_MODEL` | `openai` / `gpt-4o-mini` | Cùng model với lần chạy eval |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | `openai` / `text-embedding-3-small` | Đổi model thì phải xoá `chroma_db/` và index lại |
| `SCORE_THRESHOLD` | `0.50` | Đã calibrate, xem `threshold_calibration.json` |
| `PAGEINDEX_API_KEY` | key từ [pageindex.ai](https://pageindex.ai/developer) | Tuỳ chọn. Không có key thì fallback trả rỗng và pipeline dùng kết quả hybrid |

## Chạy lại từ đầu

```bash
# 1. Thu thập và chuẩn hoá (data đã có sẵn trong repo, chỉ chạy khi muốn tái tạo)
python -m src.task1_collect_legal_docs      # tải 3 PDF Công báo (bỏ qua file đã có)
python -m src.task2_crawl_news              # crawl 7 bài, chỉ lấy thân bài
python -m src.task3_convert_markdown        # PDF/JSON -> data/standardized/*.md

# 2. Index (bắt buộc sau khi clone hoặc khi cách chia chunk thay đổi)
python -m src.task4_chunking_indexing       # 1025 chunks vào chroma_db/; chạy lại không tạo bản trùng

# 3. (Tuỳ chọn) Calibrate lại ngưỡng fallback, rồi ghi giá trị đề xuất vào SCORE_THRESHOLD
python -m src.calibrate_threshold

# 4. (Tuỳ chọn) PageIndex: upload 3 PDF và chờ retrieval_ready=True (vài phút)
python -m src.task8_pageindex_vectorless

# 5. Evaluation A/B (dense-only vs hybrid + RRF), ghi kết quả vào group_project/evaluation/
python group_project/evaluation/run_eval.py

# 6. Chatbot
streamlit run app.py
```

Thử nhanh từng thành phần retrieval:

```bash
python -m src.task5_semantic_search "bán đồ trên mạng có phải đóng thuế không"
python -m src.task6_lexical_search "Thông tư 78/2021/TT-BTC"
python -m src.task7_reranking "Nghị định 123/2020 quy định gì về hoá đơn?"   # in ra kết quả đến từ dense hay bm25
```

`pageindex_doc_ids.json` (đã có trong `.gitignore`) lưu `doc_id` gắn với tài khoản PageIndex. Nếu dùng key khác thì xoá file này rồi chạy lại bước 4.

## Kết quả

Chi tiết trong [group_project/evaluation/RESULT.md](group_project/evaluation/RESULT.md) (RAGAS 0.4.3, 16 câu, generator và judge `gpt-4o-mini`):

| | Faithfulness | Answer relevance | Context recall | Context precision | Average | Context hit |
|---|---:|---:|---:|---:|---:|---:|
| A: dense-only | 0.958 | 0.547 | 0.938 | 0.949 | 0.848 | 13/16 |
| B: hybrid + RRF | 0.933 | 0.591 | 0.906 | 0.957 | 0.847 | 14/16 |

## Kiểm tra

```bash
pytest tests/test_contracts.py -q     # contract (không gọi network/API)
pytest tests/test_acceptance.py -q    # data, golden dataset, RESULT.md
pytest -q                             # toàn bộ (gồm test generation và PageIndex giả lập)
```

## Tài liệu

- [docs/MODULE_CONTRACTS.md](docs/MODULE_CONTRACTS.md): schema, interface và invariant giữa các module.
- [docs/STEP_BY_STEP.md](docs/STEP_BY_STEP.md), [docs/GRADING_RUBRIC.md](docs/GRADING_RUBRIC.md): hướng dẫn và rubric của bài lab.
- [group_project/evaluation/RESULT.md](group_project/evaluation/RESULT.md): kết quả đánh giá, A/B, phân tích lỗi.
- [reports/](reports/): báo cáo cá nhân theo template [reports/INDIVIDUAL_REPORT.md](reports/INDIVIDUAL_REPORT.md).
