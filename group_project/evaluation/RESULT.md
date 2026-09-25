# RAG evaluation results

## Run information

| Field                              | Value |
| ---------------------------------- | ----- |
| Evaluation date                    | 2026-09-25 (UTC 05:37) |
| Framework and version              | RAGAS 0.4.3 (`ragas.metrics.collections`), script `group_project/evaluation/run_eval.py` |
| Evaluator model                    | `gpt-4o-mini` (LLM judge) + `text-embedding-3-small` (answer relevancy) |
| Generator model                    | OpenAI `gpt-4o-mini`, temperature 0.3, top_p 0.9, cùng `SYSTEM_PROMPT` Task 10 |
| Embedding model                    | OpenAI `text-embedding-3-small` (1536 chiều), ChromaDB cosine, 1041 chunks |
| Corpus version/commit              | commit `cf4d9fe`: 3 văn bản pháp luật (NĐ 01/2021, NĐ 123/2020, TT 40/2021) + 7 bài viết; chunking `legal_article+recursive`, size 800, overlap 100 |
| Golden dataset size                | 16 câu (`golden_dataset.json`) |
| `top_k`                            | 5 (dense và BM25 lấy 10 ứng viên mỗi bên trước khi fuse) |
| Fallback threshold and calibration | `SCORE_THRESHOLD=0.57`: best dense cosine của 16 câu in-domain (min 0.589, mean 0.728) và 6 câu out/sát domain (max 0.551, mean 0.416), tách đúng 22/22 (`threshold_calibration.json`). PageIndex (Task 8) chưa triển khai nên câu dưới ngưỡng trả hybrid và LLM tự từ chối (đã thử "Thủ tục ly hôn thuận tình" → safe refusal). |

## Configurations

- **Config A — dense-only:** `_generate(q, top_k=5, use_reranking=False)`: chỉ semantic search (Task 5) lấy top 5 theo cosine, không BM25, không RRF.
- **Config B — hybrid + RRF:** `_generate(q, top_k=5, use_reranking=True)`: dense top 10 + BM25 top 10 (Task 6, tokenizer giữ số hiệu văn bản), fuse một lần bằng RRF k=60 (Task 7), lấy top 5.

Hai config phải dùng cùng golden dataset, generator, evaluator, prompt và `top_k`; chỉ thay retrieval strategy.

Ghi chú đo lường: RAGAS chấm phần nội dung câu trả lời, đã bỏ dòng disclaimer và nhãn `[Document n]` (câu trả lời gốc vẫn lưu trong `eval_results_*.json`). Lần chạy đầu để nguyên hai phần này thì answer relevancy chỉ đạt 0.058/0.037, vì RAGAS coi câu "chỉ mang tính tham khảo" là câu trả lời lảng tránh và cho 0 điểm, còn faithfulness đếm disclaimer là khẳng định không có trong context. Thử trên câu #6: relevancy 0.00 → 0.71, faithfulness 0.50 → 1.00.

## Overall scores

| Metric            | Config A | Config B | Delta B−A |
| ----------------- | -------: | -------: | --------: |
| Faithfulness      |   0.9469 |   0.9125 |   −0.0344 |
| Answer relevance  |   0.5343 |   0.5293 |   −0.0050 |
| Context recall    |   0.9375 |   0.8750 |   −0.0625 |
| Context precision |   0.9563 |   0.9776 |   +0.0213 |
| **Average**       | **0.8438** | **0.8236** | **−0.0202** |

Bổ sung (không phải metric RAGAS): `context_hit` (đầu đoạn `expected_context` có nằm nguyên văn trong top 5 không) là 11/16 ở cả hai config; không câu nào bị từ chối.

## A/B comparison

- Cấu hình tốt hơn: **Config A (dense-only)** nhỉnh hơn trên bộ 16 câu này (average 0.844 so với 0.824). Mức chênh nhỏ: −0.0625 recall tương ứng đúng một câu (#11) mất hoàn toàn context, còn −0.034 faithfulness nằm trong độ dao động của LLM judge. Chưa đủ để kết luận hybrid kém hơn nói chung.
- Evidence: B chỉ hơn ở context precision (+0.021: #10 tăng 0.53 → 0.80 vì BM25 kéo đúng dòng ngành nghề trong bảng tỷ lệ lên). B thua recall do câu #11 "Thông tư 40/2021/TT-BTC do ai ban hành": dense đưa chunk-2 (lời văn "Bộ trưởng Bộ Tài chính ban hành…") vào top 5, còn BM25 đẩy lên các chunk bảng Phụ lục gần như rỗng (chunk-177: `Điều 20. Hiệu lực thi hành \| \| \| Tỷ lệ % \|`) và RRF loại chunk-2 → recall 1.0 ở A, 0.0 ở B. Các câu tra theo số hiệu còn lại (#12, #13) đạt recall 1.0 ở cả hai config.
- Trade-off về latency/cost: token như nhau (khoảng 2.14k input và 99 output mỗi câu, một lần gọi `gpt-4o-mini`), vì chỉ khác chunk nào được đưa vào context. Latency trung bình A 3.69 s (p50 3.00 s, max 8.23 s), B 2.44 s (p50 2.38 s, max 2.99 s). Phần chênh không đến từ retrieval: A có 3 câu chậm bất thường (#1 6.7 s gồm cả cold start khởi tạo Chroma/embedding client, #3 6.6 s, #8 8.2 s) do dao động thời gian phản hồi của API OpenAI. Bỏ các câu này thì hai config tương đương khoảng 2–3 s. BM25 + RRF trên 1041 chunk chạy in-memory, tốn không đáng kể so với lời gọi LLM.

## Worst performers

|   # | Question | Config | Faithfulness | Relevancy | Recall | Precision | Failure stage | Root cause |
| --: | -------- | ------ | -----------: | --------: | -----: | --------: | ------------- | ---------- |
|   1 | Thông tư 40/2021/TT-BTC do ai ban hành và hướng dẫn về nội dung gì? (#11) | B | 0.75 | 0.70 | 0.00 | 1.00 | retrieval | Mọi chunk đều mang sẵn tiền tố tên văn bản "Thông tư 40/2021/TT-BTC…", nên token số hiệu không phân biệt được chunk nào. Các chunk bảng Phụ lục gần rỗng lại được BM25 chấm cao nhờ chuẩn hoá độ dài, và RRF trọng số bằng nhau để chúng đẩy chunk-2 (lời văn "Bộ trưởng Bộ Tài chính ban hành") ra khỏi top 5. LLM trả lời "Bộ Tài chính" thay vì "Bộ trưởng Bộ Tài chính". |
|   2 | Hộ kinh doanh nộp thuế theo phương pháp kê khai có phải sử dụng hóa đơn điện tử không? (#6) | A và B | 1.00 | 0.46 / 0.56 | 0.50 | 1.00 | data | Đáp án chuẩn dựa trên khoản 2 Điều 6 **Thông tư 78/2021/TT-BTC**, nhưng văn bản này không có trong corpus luật. Nó chỉ được nhắc trong `news/article_03.md` và `article_07.md`, nên retrieval chỉ lấy được bài báo diễn giải, không có nguyên văn quy định. Câu #15 (hộ khoán xin cấp hoá đơn lẻ) cũng thiếu nguồn gốc vì cùng lý do. |
|   3 | Hộ kinh doanh nộp thuế theo phương pháp khoán khi có nhu cầu sử dụng hóa đơn thì làm như thế nào? (#15) | B | 0.60 | 0.51 | 1.00 | 1.00 | generation | Context đủ ("cơ quan thuế cấp lẻ hóa đơn điện tử theo từng lần phát sinh"), nhưng LLM tự thêm các bước "làm đơn đề nghị", "lưu trữ chứng từ…" và một ý về chế độ kế toán không có trong đoạn được trích. Prompt chưa chặn việc diễn giải thành quy trình từng bước. |

Câu đáng chú ý khác: #14 "Chủ hộ kinh doanh có được góp vốn…" có recall 0.5 ở cả hai config. Điều 80 NĐ 01/2021 bị cắt thành nhiều chunk con: chunk-393 chứa khoản b) về người bị truy cứu trách nhiệm hình sự, còn câu "được quyền góp vốn, mua cổ phần" nằm ở chunk khác không vào top 5. Ở config B, top 1 còn là Điều 58 (góp vốn của nhà đầu tư nước ngoài) do trùng từ khoá "góp vốn, mua cổ phần".

## Recommendations

| Priority | Action | Evidence from failure analysis | Expected impact | How to verify |
| -------: | ------ | ------------------------------ | --------------- | ------------- |
| 1 | Task 4/6: không đưa tiền tố tên văn bản vào nội dung dùng cho BM25 (giữ trong metadata), và gộp hoặc bỏ các chunk bảng Phụ lục chỉ có ký tự `\|` | Worst #1: chunk-177 gần rỗng nhưng lên top vì BM25; chunk-2 bị RRF loại | Hồi phục recall #11 ở Config B; hybrid ít nhất ngang dense trên câu tra số hiệu | Chạy lại `run_eval.py --configs B`; kỳ vọng recall #11 = 1.0 và recall trung bình B ≥ A |
| 2 | Task 1–3: bổ sung **Thông tư 78/2021/TT-BTC** (hoá đơn cho hộ kinh doanh) và NĐ 70/2025/NĐ-CP vào corpus luật | Worst #2: #6 và #15 chỉ có bài báo làm nguồn cho quy định của TT 78 | Recall #6 lên 1.0, câu trả lời trích được nguyên văn Điều/Khoản thay vì bài báo | `context_hit` của #6 và #15 = True; recall ≥ 0.9 |
| 3 | Task 10: thêm luật vào `SYSTEM_PROMPT` "không suy diễn thủ tục/bước thực hiện nếu context không nêu"; đồng thời thử RRF có trọng số (dense 0.7 / BM25 0.3) | Worst #3: faithfulness 0.60 do thêm bước không có trong nguồn. B thua A 0.034 faithfulness | Faithfulness ≥ 0.95 ở cả hai config | So sánh faithfulness #15, #7 trước/sau trong `eval_results_*.json` |

## Bonus experiments

| Experiment | Baseline | Metric delta | Latency/cost delta | Conclusion |
| ---------- | -------- | -----------: | -----------------: | ---------- |
| Conversation memory: viết lại câu hỏi nối tiếp thành câu độc lập (`condense_question`) | Không nhớ ngữ cảnh: "Còn nếu bán hàng online thì sao?" retrieve theo nguyên câu mơ hồ | N/A (golden dataset là câu độc lập) | +1 lời gọi `gpt-4o-mini` cho câu có lịch sử (demo 5.8 s so với 2–3 s) | Demo thật: câu được viết lại thành "Tỷ lệ thuế GTGT và TNCN đối với dịch vụ bán hàng online là bao nhiêu?" và trả lời đúng có citation. Có test `test_follow_up_question_is_condensed_before_retrieval` |
| Highlight câu nguồn được trích (`src/citation_highlight.py`) | Chỉ hiện đoạn trích 700 ký tự đầu của chunk | N/A (tính năng UI) | So khớp từ khoá, không gọi LLM, tốn không đáng kể | Mỗi `[Document n]` được nối với câu trong nguồn có nhiều từ khoá trùng nhất và tô vàng. Có test `test_supporting_span_matches_cited_claim` |
| Reranker (Jina/BGE) | RRF | N/A | N/A | Chưa thực hiện |
| Query expansion / HyDE | Query gốc | N/A | N/A | Chưa thực hiện |
