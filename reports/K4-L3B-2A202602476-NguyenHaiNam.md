# Individual contribution report

## Thông tin

- Họ và tên: Nguyễn Hải Nam
- Mã học viên: 2A202602476
- Nhóm: Khê (Leader)
- Repository/branch: K4-L3B-RAG-Pipeline / `02476-NguyenHaiNam` (code, data, eval và README đã lên `main`; hash commit trong bảng là hash trên `main`, trừ các commit đầu của nhánh)

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Cấu hình embedding | Chốt OpenAI `text-embedding-3-small` (1536 chiều) cho cả nhóm | `.env.example`, `pyproject.toml` — `e69771b` | Done |
| Task 4 — Chunking, embedding, ChromaDB | Chia chunk văn bản luật theo cấu trúc: **Chương → Điều → recursive**. Mỗi chunk mở đầu bằng nhãn văn bản ngắn và tiêu đề Chương; bỏ chunk gần rỗng; upsert theo batch, xoá chunk cũ, kiểm tra model của collection. Index **1.025 chunk**, index lần 2 không trùng | `src/task4_chunking_indexing.py` — `bb872c8`, sửa theo kết quả eval `9218106` | Done |
| Task 5 — Dense search | score = cosine gốc `1 − distance` (Task 9 dùng để quyết định fallback) | `src/task5_semantic_search.py` — `3500941` | Done |
| Task 6 — BM25 | Tokenizer giữ số hiệu văn bản; IDF luôn dương; **chấm trên thân chunk, bỏ nhãn văn bản** | `src/task6_lexical_search.py` — `3500941`, sửa theo kết quả eval `9218106` | Done |
| Task 7 — RRF | `sum(1/(k+rank))`, một phiếu cho mỗi ID trong mỗi danh sách, không mutate input | `src/task7_reranking.py` — `753bd36` | Done |
| Calibrate `SCORE_THRESHOLD` | Chọn ngưỡng từ best dense score của 16 câu golden + **8 câu văn nói đúng domain** và 8 câu ngoài/sát domain. Kết quả **0,50** (đề xuất 0,497, accuracy 94%), thay cho 0,57 lần đầu (ngưỡng đó lệch cao) | `src/calibrate_threshold.py` — `db7738a`, `9218106`; `threshold_calibration.json` — `9218106` | Done |
| Làm lại dữ liệu (hỗ trợ Task 1–3) | Phát hiện data cũ không dùng được: PDF là file text đổi đuôi, URL `Source` trỏ sai văn bản, 4/5 bài báo là menu/404/nội dung tự viết. Thay bằng 3 PDF Công báo và 7 bài báo thật; viết lại Task 1–3 | `data/` — `01a4b88`; `src/task1–3` — `1d848a5` | Done |
| Sửa Task 8 — PageIndex fallback (hỗ trợ) | Bản trước không chạy được: import class không có trong SDK (`PageIndex`), gọi hàm không tồn tại (`client.search`), upload `.md` trong khi SDK chỉ nhận PDF, output sai contract. Viết lại theo SDK `pageindex` 0.2.8 (upload PDF gốc, `submit_query` → chờ `get_retrieval`), parse đúng response thật, metadata đúng contract, timeout 45 s để UI không treo; thêm 7 test giả lập. **Chạy thật:** câu dưới ngưỡng "shop quần áo nhỏ có cần giấy phép không" (dense 0,47) được PageIndex trả Điều 79–80 NĐ 01, trả lời có citation | `src/task8_pageindex_vectorless.py`, `tests/test_pageindex.py` — `9bc9cf4` | Done |
| Cập nhật `RESULT.md` | Ghi lại run info, overall scores, A/B, worst performers, recommendations theo lần eval sau khi sửa retrieval; thêm bảng trước/sau và demo fallback PageIndex | `group_project/evaluation/RESULT.md`, `eval_results_*.json` — `10732b2` | Done |
| Golden dataset | 16 câu; mọi `expected_context` được script kiểm tra là đoạn nguyên văn trong corpus | `golden_dataset.json` — `01a4b88` | Done |
| Leader | Chọn đề tài, chia việc A/B/C, viết kế hoạch, hướng dẫn và lý thuyết phần B; viết lại README (bảng nguồn dữ liệu, cấu hình `.env`, các bước chạy lại, ghi chú phiên bản corpus) | `docs/TEAM_PLAN.md`, `docs/GUIDE_B.md` — `5634cc7`; `README.md` — `6dc4ddf`, `277e5c3` | Done |

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** chunk văn bản luật theo cấu trúc Chương → Điều. Nội dung đưa vào dense là "nhãn văn bản + tiêu đề Chương + nội dung"; nội dung BM25 chấm thì bỏ nhãn văn bản.
   **Lý do/evidence:** bản đầu gắn **tên đầy đủ** của văn bản vào mọi chunk. Eval A/B cho thấy cách này làm hybrid thua dense: tên "…đăng ký hộ kinh doanh" lặp ở cả 477 chunk NĐ 01 nên chunk nào cũng giống nhau. Hậu quả là câu "hồ sơ đăng ký hộ kinh doanh" trả về Điều 28 (doanh nghiệp xã hội), còn Điều 87 không vào top 5; câu #11 có recall 0 ở config B. Tôi đổi sang nhãn ngắn (loại + số hiệu) cộng tiêu đề Chương (khác nhau giữa các chương), bỏ chunk gần rỗng và bảng `|`. Kết quả: Điều 87 lên hạng 2, câu #11 và #12 (Chương VIII) phục hồi recall, **average của B tăng 0,824 → 0,847**.
   **Trade-off:** phụ thuộc định dạng "Chương N / Điều N." còn nguyên sau khi convert PDF; tiêu đề chương làm mỗi chunk dài thêm tới khoảng 120 ký tự (số chunk tăng 919 → 1.025).

2. **Quyết định:** hybrid gộp dense và BM25 bằng RRF (chỉ dùng thứ hạng); BM25 dùng tokenizer giữ số hiệu văn bản kèm các phần con, và IDF kiểu Lucene.
   **Lý do/evidence:** hai phương pháp bù trừ cho nhau.
   - Query "Thông tư 78/2021/TT-BTC hộ kinh doanh sử dụng hóa đơn điện tử": BM25 hạng 1 là đúng đoạn trích Điều 6 TT 78, dense không tìm ra.
   - Query "bán đồ trên mạng có phải đóng thuế không": dense tìm đúng bài bán hàng online, BM25 hạng 1 sai (từ hiếm "đồ" có IDF 6,03 lấn át). RRF đưa chunk được cả hai tìm ra lên đầu (1/61 + 1/62 = 0,0325).
   - Sau khi sửa, B ngang A về average (−0,001) và có **context hit cao nhất (14/16 so với 13/16)**.
   **Trade-off:** chưa tách từ ghép tiếng Việt; score RRF không dùng được làm threshold.

## Kiểm thử và kết quả

- **Test hoặc query tôi đã dùng:** `pytest tests/` 35/35 pass (5 contract test phần B, 7 test PageIndex); smoke test Chroma; chạy lại Task 3 ra data giống hệt từng byte; RAGAS A/B (`run_eval.py`, cùng generator `gpt-4o-mini`) trước và sau khi sửa.
- **Kết quả trước/sau (RAGAS, 16 câu):**

  | | A dense-only | B hybrid + RRF |
  |---|---|---|
  | Average | 0,844 → 0,848 | **0,824 → 0,847** |
  | Context recall | 0,938 → 0,938 | 0,875 → 0,906 |
  | Context hit | 11 → 13/16 | 11 → **14/16** |

  Corpus: 89% chunk rác → 1.025 chunk sạch. Golden: 11/16 → 16/16 context khớp nguyên văn.
- **Lỗi đã phát hiện và cách xử lý:**
  - Tiêu đề "Chương VIII" dính vào cuối chunk Điều 78: tách tiêu đề Chương thành mục riêng.
  - Threshold 0,57 calibrate chỉ trên câu văn phong luật: "mở quán cà phê cần giấy tờ gì" (0,509) bị coi là ngoài domain. Thêm câu văn nói, ngưỡng mới 0,50.
  - PDF "signed" là bản scan không có text: chuyển sang bản Công báo.
  - Response thật của PageIndex khác tài liệu (khoá `id`, `relevant_contents` lồng list, `physical_index`): sửa parser theo response thật. Test "provider bị treo" bắt được lỗi UI phải chờ quá timeout 5 s, đã sửa.

## Điều còn hạn chế

- **Một hạn chế cụ thể của phần tôi làm:**
  - Khoảng cách threshold rất hẹp: câu đúng domain thấp nhất 0,509, câu sát domain "công ty TNHH" 0,551 vẫn vượt ngưỡng, nên phải dựa vào prompt để từ chối.
  - Câu #14 (góp vốn) vẫn chỉ recall 0,5, vì Điều 80 bị tách thành nhiều chunk con.
  - Chênh lệch giữa A và B hiện nằm trong độ dao động của LLM judge (khoảng ±0,03), nên chưa đủ căn cứ để nói hybrid tốt hơn.
  - Fallback PageIndex chậm (18–35 s mỗi câu, so với 2–3 s của hybrid) và trả đoạn đã được diễn đạt lại chứ không phải nguyên văn; endpoint retrieval đã bị PageIndex đánh dấu deprecated.
- **Nếu có thêm thời gian, thay đổi đầu tiên tôi sẽ thực hiện:** thêm reranker cross-encoder sau RRF và tách từ tiếng Việt cho BM25, đo lại context precision; mở rộng golden dataset lên khoảng 40 câu để kết luận A/B có ý nghĩa thống kê.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: 25/09/2026
- Tên thành viên: Nguyễn Hải Nam
