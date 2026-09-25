# RAG evaluation results

## Run information

| Field                              | Value |
| ---------------------------------- | ----- |
| Evaluation date                    | 2026-09-25 (UTC 13:20). Lần chạy đầu UTC 05:37, dùng để so sánh trước/sau |
| Framework and version              | RAGAS 0.4.3 (`ragas.metrics.collections`), script `group_project/evaluation/run_eval.py` |
| Evaluator model                    | `gpt-4o-mini` (LLM judge) + `text-embedding-3-small` (answer relevancy) |
| Generator model                    | OpenAI `gpt-4o-mini`, temperature 0.3, top_p 0.9, cùng `SYSTEM_PROMPT` Task 10 |
| Embedding model                    | OpenAI `text-embedding-3-small` (1536 chiều), ChromaDB cosine, **1025 chunks** |
| Corpus version/commit              | Corpus như commit `01a4b88`: 3 văn bản pháp luật (NĐ 01/2021, NĐ 123/2020, TT 40/2021, bản Công báo) + 7 bài viết. Chunking theo cấu trúc Chương → Điều → recursive (size 800, overlap 100); mỗi chunk mở đầu bằng nhãn văn bản ngắn + tiêu đề Chương; bỏ chunk gần rỗng (xem mục "Retrieval fix") |
| Golden dataset size                | 16 câu (`golden_dataset.json`), mọi `expected_context` là đoạn nguyên văn trong corpus |
| `top_k`                            | 5 (dense và BM25 lấy 10 ứng viên mỗi bên trước khi fuse) |
| Fallback threshold and calibration | `SCORE_THRESHOLD=0.50`. Calibrate trên best dense cosine của 24 câu trong domain (16 câu golden + 8 câu văn nói như "mở quán cà phê cần giấy tờ gì"; min 0.509, mean 0.670) và 8 câu ngoài/sát domain (max 0.551, mean 0.424). Ngưỡng đề xuất 0.497, accuracy 30/32 (`threshold_calibration.json`); 2 câu sát domain vượt ngưỡng ("thuế TNDN công ty TNHH" 0.551, "thành lập công ty cổ phần" 0.526) và được prompt từ chối. Ngưỡng 0.57 lần đầu chỉ calibrate trên câu golden (văn phong luật) nên lệch cao: câu văn nói đúng domain được 0.51 sẽ bị fallback nhầm. PageIndex (Task 8) chạy thật với SDK `pageindex` 0.2.8: 3 PDF luật đã upload, `retrieval_ready`. Eval A/B chạy trước khi có `PAGEINDEX_API_KEY` và mọi câu golden đều có best dense ≥ 0.50, nên không câu golden nào đi qua fallback. Demo fallback thật (xem mục cuối) |

## Configurations

- **Config A — dense-only:** `_generate(q, top_k=5, use_reranking=False)`: chỉ semantic search (Task 5) lấy top 5 theo cosine, không BM25, không RRF.
- **Config B — hybrid + RRF:** `_generate(q, top_k=5, use_reranking=True)`: dense top 10 + BM25 top 10 (Task 6, tokenizer giữ số hiệu văn bản, chấm trên thân chunk), fuse một lần bằng RRF k=60 (Task 7), lấy top 5.

Hai config dùng cùng golden dataset, generator, evaluator, prompt và `top_k`; chỉ thay retrieval strategy.

Bonus (cùng điều kiện, mỗi config chỉ khác B đúng một bước):
- **Config C — hybrid + RRF + LLM rerank:** RRF lấy 15 ứng viên, `gpt-4o-mini` xếp lại theo kiểu listwise (RankGPT) rồi lấy top 5 (`rerank_llm`, Task 7). Bật bằng `RERANKER=llm`.
- **Config D — HyDE + hybrid + RRF:** `gpt-4o-mini` viết một đoạn giả định theo văn phong văn bản luật; dense search bằng "câu hỏi + đoạn giả định", BM25 vẫn dùng câu hỏi gốc; threshold vẫn tính trên cosine của câu hỏi gốc (`src/query_expansion.py`). Bật bằng `QUERY_EXPANSION=hyde`.

Ghi chú đo lường: RAGAS chấm phần nội dung câu trả lời, đã bỏ dòng disclaimer và nhãn `[Document n]` (câu trả lời gốc vẫn lưu trong `eval_results_*.json`). Để nguyên hai phần này thì answer relevancy chỉ đạt 0.058/0.037, vì RAGAS coi câu "chỉ mang tính tham khảo" là câu trả lời lảng tránh và cho 0 điểm, còn faithfulness đếm disclaimer là khẳng định không có trong context. Thử trên câu #6: relevancy 0.00 → 0.71, faithfulness 0.50 → 1.00.

## Overall scores

| Metric            | Config A | Config B | Delta B−A |
| ----------------- | -------: | -------: | --------: |
| Faithfulness      |   0.9583 |   0.9333 |   −0.0250 |
| Answer relevance  |   0.5474 |   0.5908 |   +0.0434 |
| Context recall    |   0.9375 |   0.9062 |   −0.0313 |
| Context precision |   0.9488 |   0.9568 |   +0.0080 |
| **Average**       | **0.8480** | **0.8468** | **−0.0012** |

Bổ sung (không phải metric RAGAS): `context_hit` (đầu đoạn `expected_context` có nằm nguyên văn trong top 5 không) là **13/16 ở A và 14/16 ở B**; không câu nào bị từ chối.

### Retrieval fix sau lần eval đầu (trước/sau)

Lần eval đầu (UTC 05:37) cho B thua A −0.020 average. Phân tích worst performer chỉ ra lỗi nằm ở cách chunk (Task 4/6), không nằm ở RRF:
- Tên đầy đủ của văn bản được gắn vào mọi chunk. Ví dụ "…về đăng ký doanh nghiệp (Chương VIII: đăng ký hộ kinh doanh)" có mặt ở cả 477 chunk NĐ 01, nên chunk nào cũng giống nhau với cả dense lẫn BM25.
- Tiêu đề "Chương VIII" dính vào cuối chunk Điều 78.
- Chunk bảng Phụ lục chỉ còn ký tự `|` nhưng được BM25 chấm cao nhờ chuẩn hoá độ dài.

Đã sửa:
- Nhãn văn bản rút gọn còn loại + số hiệu, BM25 bỏ qua nhãn này.
- Tiêu đề Chương được nhận diện và gắn cho mọi Điều trong chương.
- Bảng Phụ lục chuyển thành text thường; bỏ chunk gần rỗng (1041 → 1025 chunk).

| Config B (hybrid + RRF) | Trước sửa | Sau sửa |
| ----------------------- | --------: | ------: |
| Average                 | 0.8236    | **0.8468** |
| Context recall          | 0.8750    | 0.9062  |
| Faithfulness            | 0.9125    | 0.9333  |
| Answer relevance        | 0.5293    | 0.5908  |
| Context hit             | 11/16     | 14/16   |
| #11 "TT 40/2021 do ai ban hành" (recall) | 0.00 | 1.00 |
| "Hồ sơ đăng ký hộ kinh doanh gồm những gì?": hạng của Điều 87 trong RRF | ngoài top 5 (hạng 2 là Điều 28, doanh nghiệp xã hội) | hạng 2 (top 5 đều thuộc Chương VIII hoặc bài báo về đăng ký hộ kinh doanh) |

Config A cùng lúc đổi từ 0.8438 lên 0.8480. Dense cũng hưởng lợi từ tiêu đề Chương, nhưng ít hơn nhiều so với B.

## A/B comparison

- **Cấu hình tốt hơn:** hai config **ngang nhau** (average A 0.848, B 0.847, chênh −0.001, nằm trong độ dao động của LLM judge khoảng ±0.03). Chatbot giữ **Config B làm mặc định**, vì B có context hit cao hơn (14/16 so với 13/16) và bắt được các câu tra theo số hiệu văn bản mà dense bỏ sót.
- **Evidence:**
  - **B hơn A:**
    - Answer relevance +0.043, ví dụ #1 0.55 → 0.77, #6 0.71 → 1.00.
    - Context precision +0.008: #3, #4, #7, #12 đạt 1.00 ở B (A: 0.89, 0.81, 0.95, 0.87).
    - Câu #3 "Hồ sơ đăng ký hộ kinh doanh" chỉ B có context hit.
    - Ngoài golden, query "Thông tư 78/2021/TT-BTC hộ kinh doanh sử dụng hóa đơn điện tử": BM25 hạng 1 là đúng đoạn trích Điều 6 TT 78, còn dense hạng 1 là đoạn về xử phạt.
  - **A hơn B:**
    - Faithfulness +0.025: #6 và #12 ở B được 0.67, do LLM diễn đạt thêm ý mà judge không tìm thấy trong chunk.
    - Context recall +0.031: #15 ở B mất chunk `article_03#11` ("hộ khoán sử dụng hóa đơn lẻ phải lưu trữ và xuất trình…"), vị trí này bị các chunk Chương II TT 40 thay thế sau RRF.
- **Trade-off về latency/cost:**
  - Token gần như nhau (khoảng 2.19k/2.20k input và 100/95 output mỗi câu, một lần gọi `gpt-4o-mini`), vì chỉ khác chunk nào được đưa vào context.
  - Latency trung bình A 2.18 s (p50 2.00 s, max 4.35 s), B 2.51 s (p50 2.30 s, max 3.72 s). Chênh khoảng 0.3 s chủ yếu do dao động thời gian phản hồi của API OpenAI; BM25 + RRF trên 1025 chunk chạy in-memory, tốn không đáng kể so với lời gọi LLM.

## Worst performers

|   # | Question | Config | Faithfulness | Relevancy | Recall | Precision | Failure stage | Root cause |
| --: | -------- | ------ | -----------: | --------: | -----: | --------: | ------------- | ---------- |
|   1 | Hộ kinh doanh nộp thuế theo phương pháp khoán khi có nhu cầu sử dụng hóa đơn thì làm như thế nào? (#15) | B | 0.60 | 0.49 | 0.50 | 1.00 | generation + retrieval | Đáp án chỉ có một ý ("cơ quan thuế cấp lẻ hóa đơn điện tử theo từng lần phát sinh"), nhưng LLM tự dựng quy trình "làm đơn yêu cầu cấp hóa đơn…" không có trong nguồn (A cũng chỉ đạt faithfulness 0.50). Ở B, RRF thay chunk `article_03#11` bằng các chunk Chương II TT 40 nên recall còn 0.50 (A: 1.00). Quy định gốc (khoản 2 Điều 6 TT 78/2021) không có trong corpus luật, chỉ có bài báo trích lại. |
|   2 | Chủ hộ kinh doanh có được quyền góp vốn, mua cổ phần trong doanh nghiệp không? (#14) | A và B | 0.83 / 1.00 | 0.45 / 0.44 | 0.50 | 1.00 | retrieval (B) + đo lường | Chunk đúng (khoản 2 Điều 80, `chunk-401`) đứng hạng 1 ở cả hai config và câu trả lời đúng, nhưng recall vẫn chỉ 0.50. Nhiều khả năng judge không gán được phần trích dẫn "(Điều 80 NĐ 01/2021)" của đáp án chuẩn vào context. Ở B, 4/5 chunk còn lại thuộc Chương IV/VI (góp vốn của doanh nghiệp), nhiều khả năng do BM25 khớp cụm "góp vốn, mua cổ phần". |
|   3 | Hộ kinh doanh nộp thuế theo phương pháp kê khai có phải sử dụng hóa đơn điện tử không? (#6) | A và B | 1.00 / 0.67 | 0.71 / 1.00 | 0.50 | 1.00 | data | Đáp án chuẩn dựa trên khoản 2 Điều 6 **Thông tư 78/2021/TT-BTC**, văn bản này không có trong corpus luật. Retrieval chỉ lấy được bài báo diễn giải (`article_03`), không có nguyên văn quy định, nên recall 0.50 ở cả hai config. |

Đã khắc phục so với lần eval đầu: #11 (recall B 0.00 → 1.00) và #12 "NĐ 01/2021 quy định về hộ kinh doanh tại chương nào" (recall 1.00 ở cả hai config sau khi tiêu đề Chương được gắn đúng vào các Điều của Chương VIII).

## Recommendations

| Priority | Action | Evidence from failure analysis | Expected impact | How to verify |
| -------: | ------ | ------------------------------ | --------------- | ------------- |
| 1 | Task 1–3: bổ sung **Thông tư 78/2021/TT-BTC** (hoá đơn cho hộ kinh doanh) và NĐ 70/2025/NĐ-CP vào corpus luật | Worst #1 và #3: #6 và #15 chỉ có bài báo làm nguồn cho quy định của TT 78; recall 0.50 | Recall #6, #15 lên 1.0, câu trả lời trích được nguyên văn Điều/Khoản thay vì bài báo | `context_hit` và recall của #6, #15 trong `eval_results_*.json` |
| 2 | Task 10: thêm luật vào `SYSTEM_PROMPT` "không suy diễn thủ tục/bước thực hiện nếu context không nêu" | Worst #1: faithfulness 0.50 (A) và 0.60 (B) do tự thêm bước "làm đơn yêu cầu" | Faithfulness ≥ 0.95 ở cả hai config | So sánh faithfulness #15, #6, #12 trước/sau |
| 3 | Task 7: thêm reranker sau RRF. **Đã thử (config C):** precision 0.957 → 0.983, recall 0.906 → 0.938, nhưng faithfulness giảm và tốn thêm khoảng 3k token mỗi câu. Bước tiếp: thử cross-encoder (Jina/BGE-reranker-v2-m3) để có cùng hiệu quả với chi phí thấp hơn | Worst #2: ở B, 4/5 chunk của #14 là góp vốn doanh nghiệp do BM25 khớp từ khoá; #15 mất chunk đúng do RRF | Giữ precision/recall của C, latency gần B | Chạy `run_eval.py --configs C` với cross-encoder, so với C hiện tại |

### Demo fallback PageIndex (chạy thật)

| Câu hỏi | Best dense | Nhánh | Kết quả |
| ------- | ---------: | ----- | ------- |
| "shop quần áo nhỏ có cần giấy phép không" | 0.47 | PageIndex | Trả Điều 79, 80 NĐ 01/2021; trả lời đúng (bán hàng rong được miễn đăng ký, shop quần áo phải đăng ký hộ kinh doanh), có citation, `retrieval_source="pageindex"` |
| "xuất bill cho khách thế nào" | 0.42 | PageIndex | Trả Điều 5, 6 TT 40/2021 và phần quy định chung NĐ 123/2020; trả lời có citation, `retrieval_source="pageindex"` |
| "Thủ tục ly hôn thuận tình gồm những bước nào?" | 0.45 | PageIndex → LLM từ chối | Các node PageIndex trả về không liên quan, LLM trả safe refusal, `retrieval_source="none"` |
| "Hồ sơ đăng ký hộ kinh doanh gồm những gì?" (gọi thẳng `pageindex_search`) | — | PageIndex | Điều 87 đứng hạng 1 (hybrid: hạng 2) |

Hạn chế của fallback:
- **Latency 18–35 s mỗi câu**, so với 2–3 s của hybrid, vì phải hỏi lần lượt 3 văn bản và chờ PageIndex suy luận. Có timeout 45 s nên UI không treo quá mức này.
- **`relevant_content` là đoạn PageIndex diễn đạt lại**, không phải nguyên văn (ví dụ "a) Giấy đề nghị…" thành "1. Giấy đề nghị…"), nên citation không trích được nguyên văn Điều/Khoản.
- **Endpoint retrieval đã bị PageIndex đánh dấu deprecated** (khuyên chuyển sang Chat API) nhưng hiện vẫn hoạt động.

## Bonus experiments

| Experiment | Baseline | Metric delta | Latency/cost delta | Conclusion |
| ---------- | -------- | -----------: | -----------------: | ---------- |
| Conversation memory: viết lại câu hỏi nối tiếp thành câu độc lập (`condense_question`) | Không nhớ ngữ cảnh: "Còn nếu bán hàng online thì sao?" retrieve theo nguyên câu mơ hồ | N/A (golden dataset là câu độc lập) | +1 lời gọi `gpt-4o-mini` cho câu có lịch sử (demo 5.8 s so với 2–3 s) | Demo thật: câu được viết lại thành "Tỷ lệ thuế GTGT và TNCN đối với dịch vụ bán hàng online là bao nhiêu?" và trả lời đúng có citation. Có test `test_follow_up_question_is_condensed_before_retrieval` |
| Highlight câu nguồn được trích (`src/citation_highlight.py`) | Chỉ hiện đoạn trích 700 ký tự đầu của chunk | N/A (tính năng UI) | So khớp từ khoá, không gọi LLM, tốn không đáng kể | Mỗi `[Document n]` được nối với câu trong nguồn có nhiều từ khoá trùng nhất và tô vàng. Có test `test_supporting_span_matches_cited_claim` |
| **Reranker LLM listwise** (config C: RRF top 15 → `gpt-4o-mini` xếp lại → top 5) | Config B (RRF) | Precision **+0.026** (0.957 → 0.983, cao nhất trong 4 config); recall **+0.031** (0.906 → 0.938, câu #15 phục hồi 0.5 → 1.0); faithfulness −0.042 (0.933 → 0.892, do #4 và #14 ở C: LLM thêm ý không có trong chunk); average +0.001 (0.8468 → 0.8477) | +1.2 s (2.51 → 3.72 s) và **+3.1k token** mỗi câu (1 lời gọi `gpt-4o-mini`) | Reranker cải thiện retrieval rõ nhất: câu #14 "góp vốn" từ 4/5 chunk nhiễu (Chương IV/VI về doanh nghiệp) thành 5/5 chunk Chương VIII (Điều 79–81); câu "hồ sơ đăng ký hộ kinh doanh" đưa Điều 87 lên hạng 1. Faithfulness giảm là ở bước generation, nằm trong độ dao động judge. Không bật mặc định vì chi phí token |
| **HyDE** (config D: dense search bằng câu hỏi + đoạn giả định) | Config B (câu hỏi gốc) | **Trên 14 câu văn nói (`golden_casual.json`): context recall +0.119 (0.786 → 0.905), precision +0.029, faithfulness +0.047, average +0.040 (0.717 → 0.757), context hit 5/14 → 7/14.** Trên 16 câu golden văn phong luật: average −0.005 (0.847 → 0.842), recall bằng B | +1.5–1.9 s và +275 token mỗi câu | **HyDE cải thiện câu hỏi văn nói**: dense của câu gốc lệch xa văn phong luật (cosine 0.46–0.72), đoạn giả định kéo về đúng Điều. Ví dụ "một người được mở mấy hộ kinh doanh" recall 0 → 1. Với câu golden đã viết theo văn phong luật thì HyDE không giúp thêm. Chi tiết ở mục "A/B HyDE trên câu hỏi văn nói" |

### A/B HyDE trên câu hỏi văn nói

Golden dataset viết theo văn phong luật nên không đo được tác dụng của HyDE. Nhóm thêm `golden_casual.json`: 14 câu hỏi viết như người dùng thật (không dùng thuật ngữ pháp lý), mỗi câu có `expected_context` là đoạn nguyên văn trong corpus, viết và gán đáp án trước khi chạy. Chạy `run_eval.py --golden group_project/evaluation/golden_casual.json --tag casual --configs B D`; kết quả ở `eval_summary_casual.json`, `eval_results_casual_*.json`. Hai config dùng cùng generator, judge, prompt, `top_k`, threshold; D chỉ khác B ở bước HyDE.

| Metric            | B: hybrid + RRF | D: HyDE + hybrid | Delta D−B |
| ----------------- | --------------: | ---------------: | --------: |
| Faithfulness      | 0.7770 | 0.8238 | +0.0468 |
| Answer relevance  | 0.4111 | 0.3744 | −0.0367 |
| Context recall    | 0.7857 | **0.9048** | **+0.1191** |
| Context precision | 0.8940 | 0.9233 | +0.0293 |
| **Average**       | **0.7169** | **0.7566** | **+0.0397** |
| Context hit       | 5/14 | 7/14 | +2 |
| Latency trung bình | 6.78 s | 8.32 s | +1.54 s |

- Recall theo từng câu: D thắng 4 câu (#3 "một người được mở mấy hộ kinh doanh" 0 → 1; #5 "có được làm chủ doanh nghiệp tư nhân nữa không" 0.5 → 1; #6 0.5 → 1; #11 "bán hàng trên facebook" 0.5 → 1), thua 2 câu (#4 "bán hàng rong" 1 → 0.5; #7 "dẹp hộ kinh doanh" 1 → 0.67).
- #6 và #8 có best dense < 0.50 nên đi qua PageIndex ở cả hai config; chênh lệch ở hai câu này đến từ PageIndex/judge, không phải HyDE.
- Answer relevance giảm nhẹ (−0.037) và faithfulness của một số câu (#10, #12, #13) giảm ở D: đoạn chunk khác làm LLM diễn đạt khác; không có câu nào bị từ chối.
- Latency ở tập này cao hơn tập golden vì 2/14 câu đi qua PageIndex (18–35 s mỗi câu).
- Hạn chế: tập nhỏ (14 câu); mức tăng recall +0.12 lớn hơn nhiều so với độ dao động của judge (khoảng ±0.03) nhưng cần tập lớn hơn để khẳng định chắc chắn.
