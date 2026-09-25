# Individual contribution report

## Thông tin

- Họ và tên: Bùi Phương Duy
- Mã học viên: 2A202602684
- Nhóm: Khê (người C: pipeline, generation, chatbot, evaluation)
- Repository/branch: K4-L3B-RAG-Pipeline / `BuiPhuongDuy_2A202602684`. Code đã lên `main` trong commit `c6296ac` (gộp các commit `7037861`, `8adb39e`, `38a40a2` của nhánh)

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Task 9 — Retrieval pipeline | `retrieve()`: dense + BM25 lấy `top_k*2`, RRF chạy đúng một lần; quyết định fallback theo **cosine gốc của dense**, không theo điểm RRF; PageIndex lỗi hoặc rỗng thì trả hybrid; một retriever lỗi không kéo sập pipeline; đọc `SCORE_THRESHOLD` từ `.env`; `use_reranking=False` là Config A | `src/task9_retrieval_pipeline.py` — `c6296ac` (Nam thêm nhánh reranker/HyDE ở `51db58f`) | Done |
| Task 10 — Generation có citation | `reorder_for_llm` không mutate; `format_context` ghi `[Document n \| Title \| Số hiệu \| Điều \| Source]`; `call_llm` 3 nhánh OpenAI/Gemini/Anthropic có timeout và đếm token; `SYSTEM_PROMPT` theo mục 4.3 (citation, ưu tiên văn bản mới hơn, disclaimer, từ chối ngoài phạm vi); đánh lại số citation sau reorder; safe refusal khi không có chunk, provider lỗi hoặc LLM tự từ chối; tách `_generate()` cho A/B | `src/task10_generation.py`, `tests/test_generation.py` (9 test mock) — `c6296ac` | Done |
| Chatbot `app.py` | Streamlit: citation hiển thị thành con dấu có tooltip; phiếu nguồn ghi tên văn bản, số hiệu, Điều, score, retrieval method, link; câu hỏi mẫu và disclaimer ở sidebar; chọn hybrid/dense để demo A/B; khung từ chối riêng; `session_state`; bắt lỗi để UI không crash | `app.py`, `.streamlit/config.toml` — `c6296ac` | Done |
| Evaluation | `run_eval.py`: RAGAS 0.4.3 với 4 metric, cùng generator/prompt/top_k/judge cho hai config; đo latency và token; lưu output thô theo từng câu (JSON/CSV). Chạy lần eval đầu, viết bản RESULT.md đầu tiên và phân tích worst performers | `group_project/evaluation/run_eval.py`, `RESULT.md` — `c6296ac` (Nam thêm config C/D ở `51db58f`, chạy lại sau khi sửa retrieval ở `10732b2`) | Done |
| Bonus: conversation memory (+2) | `condense_question()` viết lại câu hỏi nối tiếp thành câu độc lập trước khi retrieve; UI có nút bật/tắt và dòng "Đã hiểu câu hỏi là…" | `src/task10_generation.py`, `app.py` — `c6296ac` | Done |
| Bonus: highlight citation (+2) | `src/citation_highlight.py` nối mỗi `[Document n]` với câu trong nguồn có nhiều từ khoá trùng nhất; UI tô vàng câu đó và tô màu tên Điều/Khoản | `src/citation_highlight.py`, `app.py` — `c6296ac` | Done |
| Dọn repo | Chuyển RESULT.md về `group_project/evaluation/` cho khớp acceptance test; thêm `chroma_db/`, `.streamlit/secrets.toml` vào `.gitignore`; sửa docstring `src/__init__.py` | `c6296ac` | Done |

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** khi chấm RAGAS, bỏ dòng disclaimer và nhãn `[Document n]` khỏi câu trả lời; người dùng vẫn thấy đầy đủ cả hai.
   **Lý do/evidence:** lần chạy đầu, answer relevancy chỉ đạt 0.058 (A) và 0.037 (B), trong khi recall và precision khoảng 0.95. Tôi thử lại trên cùng câu #6: câu trả lời nguyên bản được relevancy 0.00 và faithfulness 0.50, còn phần nội dung được 0.71 và 1.00. RAGAS coi câu "chỉ mang tính tham khảo" là câu trả lời lảng tránh (cho 0 điểm) và coi disclaimer là khẳng định không có trong context.
   **Trade-off:** điểm phản ánh nội dung chứ không phải nguyên văn người dùng thấy. Tôi ghi rõ trong RESULT.md và lưu cả `answer` lẫn `scored_answer` để đối chiếu.

2. **Quyết định:** đánh lại số citation sau `reorder_for_llm`. Khi LLM tự từ chối mà không trích nguồn nào, trả về dạng safe refusal (`sources=[]`, `retrieval_source="none"`) và giữ các chunk đã xét trong key phụ `retrieved`.
   **Lý do/evidence:** context bị đảo thứ tự để giảm lost-in-the-middle, còn `sources` giữ thứ tự theo score. Nếu không dịch lại số thì `[Document 2]` sẽ trỏ sai nguồn (test `test_citations_are_remapped_to_sources_order`). Khi chạy thật câu "Thủ tục ly hôn…", LLM từ chối nhưng vẫn kèm 5 nguồn không liên quan, khiến UI hiển thị như một câu trả lời bình thường.
   **Trade-off:** thêm key `retrieved` ngoài contract (validator vẫn pass). `run_eval.py` dùng key này để vẫn chấm được retrieval khi câu trả lời là từ chối.

## Kiểm thử và kết quả

- **Test hoặc query tôi đã dùng:**
  - `pytest -q` trên `main`: 41/41 pass. Clone sạch repo rồi chạy lại cũng 41/41.
  - `run_eval.py` trên 16 câu golden.
  - Chạy thật `streamlit run app.py` với index 1025 chunk: câu trong domain, tra theo số hiệu (NĐ 123/2020), câu ngoài domain (ly hôn → safe refusal), câu nối tiếp "Còn nếu bán hàng online thì sao?" (được viết lại đúng, có citation và highlight). Chụp màn hình bằng Chrome headless để kiểm tra UI trên desktop và mobile.
- **Kết quả trước/sau:**
  - Sửa lỗi đo: answer relevancy 0.058 → 0.534 (A).
  - Lần eval đầu của tôi: A 0.844, B 0.824. Phân tích worst performer chỉ ra câu #11 có recall 0.00 ở B vì mọi chunk đều mang tên đầy đủ của văn bản và BM25 chấm cao các chunk bảng Phụ lục gần rỗng. Đây là đề xuất ưu tiên 1 tôi ghi trong RESULT.md.
  - Nam sửa chunking theo đề xuất đó (`9218106`), sau đó: A 0.848, B 0.847, #11 recall 0.00 → 1.00, context hit của B 11/16 → 14/16.
- **Lỗi đã phát hiện và cách xử lý:**
  - Lỗi đo do disclaimer (đã nêu ở trên).
  - LLM từ chối nhưng vẫn kèm nguồn: đã chuẩn hoá thành safe refusal.
  - API key bị dán nhầm vào dòng `LLM_MODEL` và lộ ra trong file summary tạm: đã chuyển key sang `OPENAI_API_KEY` và xoá file đó (key chưa từng được commit).
  - `.gitignore` bị chèn nhầm dòng `data/`: đã gỡ trước khi push.
  - Khi chạy lại trên `main`, máy tôi còn index cũ (1041 chunk) và ngưỡng 0.57: đã index lại (1025) và đổi về 0.50 theo lần calibrate mới của nhóm.

## Điều còn hạn chế

- **Một hạn chế cụ thể của phần tôi làm:**
  - Generation đôi khi gắn citation vào một nguồn chỉ liên quan một phần. Ví dụ trong demo câu nối tiếp về bán hàng online, mức lệ phí môn bài được gắn `[Document 5]`, trong khi nguồn này là Điều 9 TT 40 (cho thuê tài sản).
  - Đề xuất 2 trong RESULT.md (thêm vào prompt luật "không suy diễn thủ tục") chưa được triển khai. Faithfulness của #15 vẫn chỉ 0.50–0.60.
  - Highlight chỉ so khớp từ khoá, nên có thể tô sai câu khi nguồn dùng từ đồng nghĩa.
- **Nếu có thêm thời gian, thay đổi đầu tiên tôi sẽ thực hiện:** dùng `supporting_spans()` để kiểm tra từng citation sau khi LLM trả lời: citation nào không có câu nguồn đủ khớp thì đánh dấu hoặc bỏ. Kết hợp với luật mới trong `SYSTEM_PROMPT`, rồi chạy lại `run_eval.py --configs A B` để so faithfulness của #15, #6, #12 trước và sau.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: 26/09/2026
- Tên thành viên: Bùi Phương Duy
