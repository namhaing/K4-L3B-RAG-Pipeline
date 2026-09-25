# Individual contribution report

## Thông tin

- Họ và tên: Nguyễn Hải Nam
- Mã học viên: 2A202602476
- Nhóm: Khê (Leader)
- Repository/branch: K4-L3B-RAG-Pipeline / `02476-NguyenHaiNam`

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Cấu hình embedding | Chốt OpenAI `text-embedding-3-small` (1536 chiều) cho cả nhóm; thêm `EMBEDDING_DIM` tự suy ra theo model | `.env.example`, `pyproject.toml` — `e69771b` | Done |
| Task 4 — Chunking, embedding, ChromaDB | Chunk văn bản luật theo "Điều N." và gắn tên văn bản vào đầu mỗi chunk; dispatch 3 embedding provider; parse header Markdown ra metadata; upsert theo batch và xoá chunk cũ | `src/task4_chunking_indexing.py` — `bb872c8` | Done (code + test); index corpus thật: Blocked, chờ data |
| Task 5 — Dense search | score = cosine gốc `1 − distance`, dedupe, khôi phục `url=None` | `src/task5_semantic_search.py` — `3500941` | Done |
| Task 6 — BM25 | Tokenizer giữ số hiệu văn bản; IDF luôn dương; lazy-load corpus từ Chroma | `src/task6_lexical_search.py` — `3500941` | Done |
| Task 7 — RRF | `sum(1/(k+rank))`, một phiếu cho mỗi ID trong mỗi danh sách, không mutate input | `src/task7_reranking.py` — `753bd36` | Done |
| Calibrate `SCORE_THRESHOLD` | Script so sánh best dense score giữa câu trong domain và ngoài domain, chọn ngưỡng, lưu evidence JSON | `src/calibrate_threshold.py` — `db7738a` | Partial: đã có script, chờ golden dataset |
| Leader — kế hoạch nhóm | Phân tích repo và rubric, chọn đề tài, chia việc A/B/C, viết hướng dẫn phần B | `docs/TEAM_PLAN.md`, `docs/GUIDE_B.md`, `TEAMMATES.md` — `5634cc7` | Done |

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** chunk văn bản luật theo "Điều N." rồi mới cắt recursive; gắn tên văn bản (có số hiệu) vào đầu mỗi chunk.
   **Lý do/evidence:** mỗi Điều là một đơn vị nghĩa trọn vẹn, và metadata `article` giúp citation ghi được "Điều 4". Số hiệu văn bản ("40/2021/TT-BTC") chỉ nằm ở trang đầu, nên các chunk ở Điều sau không chứa nó. Trong smoke test, trước khi gắn tên thì query "Thông tư 40/2021" chỉ khớp 1/5 chunk; sau khi gắn thì khớp 5/5. Trên data hiện có, chia theo Điều cho ra 15 chunk, mỗi Điều một chunk; recursive thuần cho ra 8 chunk cắt ngang giữa các Điều.
   **Trade-off:** phụ thuộc định dạng "Điều N." còn nguyên sau khi convert PDF; mỗi chunk dài thêm khoảng 150 ký tự; Điều quá ngắn tạo chunk nhỏ.

2. **Quyết định:** BM25 dùng tokenizer bằng regex giữ nguyên số hiệu văn bản (và thêm các phần con), với IDF kiểu Lucene `log(1 + (N−n+0.5)/(n+0.5))`.
   **Lý do/evidence:** người dùng hay tra theo số hiệu, và query "123/2020" vẫn khớp với "123/2020/NĐ-CP" nhờ các phần con. IDF của `BM25Okapi` gốc bằng 0 khi một từ xuất hiện ở đúng nửa corpus: với contract test 2 chunk, code mẫu trả về rỗng và fail; bản đã sửa pass.
   **Trade-off:** chưa tách từ ghép tiếng Việt ("hộ kinh doanh" thành 3 token rời), nên BM25 kém chính xác hơn so với dùng word segmentation.

## Kiểm thử và kết quả

- **Test hoặc query tôi đã dùng:**
  - `pytest tests/test_contracts.py`: 5 test phần B (signature, chunk, semantic, lexical, RRF) đều pass. Kết quả chung là 11 passed, 4 failed; 4 test fail là Task 9–10 chưa được implement.
  - Smoke test với Chroma thật (data và embedding giả) kiểm tra: parse header, chia theo Điều, index 2 lần không trùng, xoá chunk thừa khi tài liệu ngắn lại, khôi phục `url`, output của dense/BM25/RRF đúng contract.
- **Kết quả trước/sau:** BM25 khớp số hiệu tăng từ 1/5 lên 5/5 chunk sau khi gắn tên văn bản vào chunk. Chunk bài báo không còn bắt đầu bằng ". " (dùng `keep_separator="end"`).
- **Lỗi đã phát hiện và cách xử lý:**
  - Chroma không lưu được `url=None`: bỏ key khi index và khôi phục khi đọc ra.
  - Regex chỉ nhận "Điều" có dấu nên data đầu tiên (không dấu) cho `article=None` ở mọi chunk: cho regex nhận thêm "Dieu".
  - Data legal đầu tiên là PDF tự tạo bằng fpdf2, bị mất dấu tiếng Việt: đã báo người phụ trách Task 1 tải lại văn bản gốc.

## Điều còn hạn chế

- **Một hạn chế cụ thể của phần tôi làm:** chưa index và calibrate threshold trên corpus thật (đang chờ data chuẩn và golden dataset), nên chưa có số liệu retrieval thực tế.
- **Nếu có thêm thời gian, thay đổi đầu tiên tôi sẽ thực hiện:** thêm tách từ tiếng Việt (`pyvi`) cho BM25 và reranker `bge-reranker-v2-m3`/Jina sau RRF, so sánh context precision với RRF trên golden dataset.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: 25/09/2026
- Tên thành viên: Nguyễn Hải Nam
