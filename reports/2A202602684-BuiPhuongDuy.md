# Individual contribution report

## Thông tin

- Họ và tên: Bùi Phương Duy
- Mã học viên: 2A202602684
- Nhóm: Khê
- Repository/branch: https://github.com/namhaing/K4-L3B-RAG-Pipeline (branch `BuiPhuongDuy_2A202602684`)

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Task 9 — Retrieval pipeline | `retrieve()`: dense + BM25 lấy `top_k*2`, fuse RRF đúng một lần, so ngưỡng fallback với cosine gốc của dense; PageIndex lỗi hoặc rỗng thì trả hybrid; một retriever lỗi không làm sập pipeline; `use_reranking=False` là Config A dense-only; ngưỡng mặc định 0.57 theo kết quả calibrate | `src/task9_retrieval_pipeline.py` (commit `7037861`, `cf4d9fe`) | Done |
| Task 10 — Generation có citation | `reorder_for_llm`, `format_context` (kèm số hiệu, Điều, ngày hiệu lực), `call_llm` 3 provider có timeout và đếm token, `SYSTEM_PROMPT` theo domain (citation, ưu tiên văn bản mới hơn, disclaimer, từ chối ngoài phạm vi), đánh lại số citation sau reorder, safe refusal khi retrieval rỗng, provider lỗi hoặc LLM tự từ chối; `_generate()` dùng chung cho A/B | `src/task10_generation.py`, `tests/test_generation.py` | Done |
| Chatbot `app.py` | Giao diện Streamlit: citation hiển thị thành con dấu có tooltip; phiếu nguồn ghi số hiệu, Điều, điểm, retrieval method, link; câu hỏi mẫu; chọn hybrid/dense; khung từ chối; disclaimer; `session_state`; bắt lỗi | `app.py`, `.streamlit/config.toml` | Done |
| Evaluation A/B | `run_eval.py`: RAGAS 0.4.3 với 4 metric cho Config A và B, cùng generator, prompt, top_k và evaluator; đo latency và token; lưu output thô JSON/CSV; phát hiện và sửa lỗi đo do disclaimer; chạy thật trên 16 câu và điền `RESULT.md` | `group_project/evaluation/run_eval.py`, `eval_results_{A,B}.json`, `eval_results.csv`, `eval_summary.json`, `RESULT.md` | Done |
| Bonus: conversation memory (+2) | `condense_question()` viết lại câu hỏi nối tiếp thành câu độc lập trước khi retrieve; UI có nút bật/tắt và hiện "Đã hiểu câu hỏi là…" | `src/task10_generation.py`, `app.py` | Done |
| Bonus: highlight citation (+2) | `src/citation_highlight.py` nối mỗi `[Document n]` với câu trong nguồn khớp nhất và tô sáng trên UI | `src/citation_highlight.py`, `app.py` | Done |

Bằng chứng: `pytest -q` pass 28/28 (gồm 9 test mock của tôi trong `tests/test_generation.py`); kết quả eval thật trong `group_project/evaluation/eval_summary.json`.

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** Khi chấm RAGAS, bỏ dòng disclaimer và nhãn `[Document n]` khỏi câu trả lời, nhưng vẫn giữ chúng trong câu trả lời gửi người dùng.
   **Lý do/evidence:** Lần chạy đầu, answer relevancy chỉ đạt 0.058 (A) và 0.037 (B), dù recall và precision khoảng 0.95. Tôi thử lại trên cùng câu #6: nguyên bản cho relevancy 0.00 và faithfulness 0.50, còn phần nội dung cho 0.71 và 1.00. RAGAS coi câu "chỉ mang tính tham khảo" là câu trả lời lảng tránh (cho 0 điểm), và coi disclaimer là khẳng định không có trong context.
   **Trade-off:** Điểm eval phản ánh nội dung chứ không phản ánh nguyên văn người dùng thấy. Tôi ghi rõ điều này trong RESULT.md và lưu cả `answer` lẫn `scored_answer` để đối chiếu.

2. **Quyết định:** Đánh lại số citation `[Document n]` sau reorder, và khi LLM tự từ chối mà không có citation thì trả về dạng safe refusal (`sources=[]`, `retrieval_source="none"`), đồng thời giữ các chunk đã xét trong key `retrieved`.
   **Lý do/evidence:** Context được reorder để giảm lost-in-the-middle, còn `sources` giữ thứ tự theo điểm, nên phải dịch lại số thì citation mới trỏ đúng nguồn (test `test_citations_are_remapped_to_sources_order`). Khi chạy thật câu "Thủ tục ly hôn…", LLM từ chối nhưng vẫn kèm 5 nguồn không dùng tới, khiến UI hiển thị như một câu trả lời bình thường.
   **Trade-off:** Thêm key phụ `retrieved` ngoài contract; eval dùng key này để vẫn chấm được retrieval khi câu trả lời là từ chối.

## Kiểm thử và kết quả

- Test hoặc query tôi đã dùng: `pytest -q`; `run_eval.py` trên 16 câu golden cho hai config; demo thật 4 kịch bản: câu trong domain, tra theo số hiệu NĐ 123/2020, câu ngoài domain (ly hôn), câu nối tiếp "Còn nếu bán hàng online thì sao?"; chụp màn hình UI bằng Chrome headless để kiểm tra highlight và memory.
- Kết quả trước/sau nếu có: average RAGAS A 0.844 / B 0.824 (faithfulness 0.947 / 0.913, recall 0.938 / 0.875, precision 0.956 / 0.978). Answer relevancy tăng từ 0.058 lên 0.534 sau khi sửa lỗi đo. `pytest` đi từ 8 test fail (khi Task 4–7 chưa có) lên 28/28 pass.
- Lỗi đã phát hiện và cách xử lý: (1) lỗi đo do disclaimer, đã nêu ở trên; (2) API key bị dán nhầm vào dòng `LLM_MODEL` trong `.env` và lộ ra trong summary eval, tôi đã chuyển key sang `OPENAI_API_KEY` và xoá file output chứa key; (3) `.gitignore` bị chèn nhầm dòng `data/`, tôi gỡ trước khi push; (4) model Claude mới không nhận đồng thời `temperature` và `top_p`, nên nhánh Anthropic chỉ truyền `temperature`.

## Điều còn hạn chế

- Một hạn chế cụ thể của phần tôi làm: highlight chỉ so khớp từ khoá nên có thể tô sai câu khi nguồn dùng từ đồng nghĩa. Ngoài ra, khi PageIndex (Task 8) chưa có, câu hỏi dưới ngưỡng vẫn phải dựa vào LLM để từ chối, chưa có bước chặn cứng ở pipeline.
- Nếu có thêm thời gian, thay đổi đầu tiên tôi sẽ thực hiện: cùng người B bỏ tiền tố tên văn bản khỏi nội dung BM25 và gộp các chunk bảng Phụ lục rỗng (nguyên nhân khiến câu #11 của Config B có recall 0.0), rồi chạy lại `run_eval.py --configs B` để kiểm chứng.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: 2026-09-25
- Tên thành viên: Bùi Phương Duy
