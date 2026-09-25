# Kế hoạch nhóm — Chatbot RAG "Pháp luật cho hộ kinh doanh"

## 1. Tổng quan

**Đề tài:** chatbot trả lời câu hỏi về **pháp luật dành cho hộ kinh doanh cá thể**: đăng ký kinh doanh, thuế, kê khai, hoá đơn điện tử và bán hàng qua thương mại điện tử. Mỗi câu trả lời phải trích dẫn văn bản pháp luật hoặc bài viết làm nguồn. Chatbot từ chối khi câu hỏi nằm ngoài phạm vi hoặc không đủ căn cứ.

**Người dùng mục tiêu:** người chuẩn bị mở hoặc đang vận hành hộ kinh doanh nhỏ (quán ăn, tạp hoá, bán hàng online), cần câu trả lời nhanh và có căn cứ pháp lý.

**Hiện trạng repo:** chưa có dữ liệu. Code chỉ là khung: mọi hàm đều `raise NotImplementedError`, phần gợi ý nằm trong comment.

### Luồng pipeline

```
Task1 PDF/DOCX văn bản pháp luật ─┐
                                  ├─► Task3 Markdown ─► Task4 chunk theo Điều + embed + ChromaDB
Task2 crawl bài hướng dẫn (JSON) ─┘                          │
                              ┌──────────────────────────────┴──────────┐
                        Task5 dense (cosine)                     Task6 BM25 (bắt số hiệu văn bản)
                              └──────────────► Task7 RRF ◄──────────────┘
                                                   │
                  Task9 retrieve(): dense score < threshold ─► Task8 PageIndex (cây Chương/Điều)
                                                   │
                  Task10 generate_with_citation() ─► app.py (Streamlit) ─► Evaluation (RAGAS, A/B)
```

### Vì sao đề tài này hợp với bài

| Tiêu chí rubric | Lý do phù hợp |
|---|---|
| Dữ liệu có nguồn rõ ràng | Văn bản pháp luật có số hiệu, cơ quan ban hành, ngày hiệu lực, tải được từ cổng `.gov.vn` |
| Dense + BM25 + RRF (20đ) | Câu hỏi có số hiệu như "Thông tư 40/2021" thì BM25 thắng; câu hỏi tự nhiên như "bán hàng online có phải đóng thuế không" thì dense thắng. Hybrid có lý do rõ ràng để tồn tại |
| Generation có citation | Câu trả lời pháp lý bắt buộc phải có căn cứ (Điều, Khoản, văn bản) |
| Safe refusal | Dễ tạo query ngoài domain (ly hôn, giá vàng) và query sát domain (thuế của công ty TNHH) để demo |
| Golden dataset | Đáp án rõ ràng (ngưỡng doanh thu, tỷ lệ %, hồ sơ, thời hạn), nên chấm faithfulness và recall chính xác |

### File quan trọng trong repo

| File | Vai trò |
|---|---|
| [MODULE_CONTRACTS.md](MODULE_CONTRACTS.md) | Schema `Document` / `SearchResult` / `GenerationResult` và invariant. Mọi module phải tuân theo |
| [../src/contracts.py](../src/contracts.py) | Validator mà test sử dụng |
| [../tests/test_contracts.py](../tests/test_contracts.py) | Unit test dùng mock, không gọi network |
| [../tests/test_acceptance.py](../tests/test_acceptance.py) | Kiểm tra dữ liệu, golden dataset, RESULT.md |
| [GRADING_RUBRIC.md](GRADING_RUBRIC.md) | Thang điểm: 90 điểm chính + tối đa 10 điểm bonus |

---

## 2. Bộ dữ liệu

### 2.1. Văn bản pháp luật (Task 1, cần ≥3, nên lấy 4–6)

Đây là **danh sách ứng viên**. Người A phải **xác minh số hiệu, tình trạng hiệu lực và văn bản sửa đổi/thay thế mới nhất** trước khi dùng, vì chính sách thuế với hộ kinh doanh đang thay đổi nhiều từ năm 2025–2026.

| Nhóm nội dung | Văn bản ứng viên (kiểm tra lại hiệu lực) | Câu hỏi mà văn bản trả lời |
|---|---|---|
| Đăng ký hộ kinh doanh | Nghị định về đăng ký doanh nghiệp, phần hộ kinh doanh (NĐ 01/2021/NĐ-CP hoặc văn bản thay thế) | Ai được đăng ký, hồ sơ, nơi nộp, thời hạn cấp giấy |
| Thuế hộ, cá nhân kinh doanh | Thông tư 40/2021/TT-BTC và văn bản sửa đổi; các quy định mới về bỏ thuế khoán | Ngưỡng doanh thu chịu thuế, tỷ lệ % theo ngành, phương pháp khoán/kê khai |
| Hoá đơn điện tử | Nghị định 123/2020/NĐ-CP và văn bản sửa đổi (NĐ 70/2025/NĐ-CP) | Khi nào phải dùng hoá đơn, hoá đơn từ máy tính tiền |
| Thuế với thương mại điện tử | Nghị định về quản lý thuế với hoạt động kinh doanh trên nền tảng TMĐT (NĐ 117/2025/NĐ-CP) | Sàn khấu trừ thuế thay, bán qua Facebook/Shopee |

**Nguồn ưu tiên:** `vanban.chinhphu.vn`, `datafiles.chinhphu.vn`, cổng của cơ quan thuế, `dangkykinhdoanh.gov.vn`.
**Tránh** crawl `thuvienphapluat.vn` vì trang này chặn bot và có điều khoản sử dụng. Không vượt WAF.

### 2.2. Bài viết hướng dẫn (Task 2, cần ≥5, nên lấy 6–8)

- Bài hướng dẫn trên Báo Chính phủ, cổng cơ quan thuế và báo lớn (VnExpress, Tuổi Trẻ, Thanh Niên…) về: thủ tục đăng ký hộ kinh doanh, cách tính thuế, chuyển từ thuế khoán sang kê khai, hoá đơn máy tính tiền, thuế khi bán hàng online.
- Chọn bài **có ngày đăng**, ưu tiên bài mới. Ghi lại ngày đăng để xử lý trường hợp bài cũ mâu thuẫn với quy định mới (xem 4.3).

### 2.3. Bảng nguồn (đưa vào README)

| File | Loại | Tên văn bản / bài viết | Số hiệu | Cơ quan / báo | Ngày ban hành / đăng | Hiệu lực | URL | Ngày thu thập |
|---|---|---|---|---|---|---|---|---|

---

## 3. Vấn đề kỹ thuật cần sửa trước

1. **Đường dẫn báo cáo không khớp:** test đọc `group_project/evaluation/RESULT.md`, nhưng file đang nằm ở `reports/RESULT.md`. README còn trỏ tới thư mục `group_project/ịndividual/` không tồn tại. Cần chuyển file và sửa link.
2. **`group_project/evaluation/golden_dataset.json` rỗng (0 byte).**
3. ✅ **Embedding đã chốt: OpenAI `text-embedding-3-small`** (1536 chiều). `.env.example` đã cập nhật. Cả nhóm dùng chung `OPENAI_API_KEY` cho cả embedding và LLM. `sentence-transformers` giữ comment trong `pyproject.toml`. Đổi model thì phải xoá `chroma_db/` rồi index lại.
4. **Chưa có script evaluation**, phải tự viết bằng RAGAS.
5. **Các bẫy test cần biết:**
   - Task 9 gọi `rerank_rrf([dense, sparse], top_k=...)`, không truyền `k=`. Test mock bằng `lambda lists, top_k`. Chỉ fuse **một lần**.
   - Task 6: biến global `CORPUS` bị test monkeypatch. Chỉ lazy-load khi `CORPUS` rỗng.
   - Task 4 không được load model hoặc gọi API lúc import.
   - Mỗi chunk dài tối đa `CHUNK_SIZE * 1.1`, kể cả khi chunk theo Điều (Điều dài thì phải cắt tiếp).
6. **Làm A/B không đúng cách sẽ gây lỗi:**
   - Test khoá signature `generate_with_citation(query, top_k)`, nên không thêm tham số được. Config A (dense-only) phải gọi qua hàm nội bộ `_generate(query, top_k, use_reranking)`.
   - Dense-only trả `retrieval_method="dense"`, nhưng `retrieval_source` chỉ nhận `hybrid | pageindex | none`, nên phải map `dense` → `hybrid`.
7. **`chroma_db/` chưa có trong `.gitignore`.**

---

## 4. Thiết kế riêng cho domain pháp luật

### 4.1. Chunking theo cấu trúc văn bản (Task 4)

- Văn bản pháp luật có cấu trúc **Chương → Mục → Điều → Khoản → Điểm**. Nên tách trước theo `Điều \d+`, sau đó mới cắt tiếp bằng `RecursiveCharacterTextSplitter` nếu Điều dài hơn `CHUNK_SIZE`.
- Thêm metadata mở rộng (ngoài các key bắt buộc; Chroma chỉ nhận giá trị scalar): `doc_number` (ví dụ `40/2021/TT-BTC`), `article` (ví dụ `Điều 4`), `issued_date`, `effective_date`.
- Chèn tiêu đề Điều vào đầu mỗi chunk con để chunk không bị mất ngữ cảnh.
- Bài báo thì chunk theo heading/đoạn như bình thường.

### 4.2. BM25 cho tiếng Việt pháp lý (Task 6)

- Tokenizer **giữ nguyên số hiệu** như `123/2020/NĐ-CP` và `40/2021/TT-BTC`, không tách theo `/` hoặc `-`.
- Chuẩn hoá: lowercase và Unicode NFC. Có thể map từ viết tắt (`NĐ` ↔ `nghị định`, `TT` ↔ `thông tư`, `HKD` ↔ `hộ kinh doanh`).
- Tuỳ chọn tách từ tiếng Việt (`pyvi`/`underthesea`) và so sánh trước/sau.

### 4.3. Prompt và câu trả lời (Task 10)

- Chỉ trả lời từ context. Mỗi ý phải có citation `[Document n]` và nêu tên văn bản kèm Điều nếu có.
- **Khi các nguồn mâu thuẫn** (ví dụ bài báo cũ nói về thuế khoán trong khi quy định mới đã thay đổi): ưu tiên văn bản pháp luật có hiệu lực mới hơn và nói rõ mốc thời gian.
- Luôn kèm dòng lưu ý: *"Thông tin chỉ mang tính tham khảo, không thay thế tư vấn pháp lý."*
- Từ chối lịch sự với câu hỏi ngoài phạm vi, ví dụ luật hôn nhân, hình sự, hay thuế của doanh nghiệp lớn.

### 4.4. PageIndex fallback (Task 8)

- PageIndex dựng cây mục lục (Chương/Điều), hợp với văn bản pháp luật dài. Đây là lý do dùng nó làm fallback khi dense score thấp.

---

## 5. Golden dataset (≥15 câu, nên làm 18–20)

Mỗi mục có `question`, `expected_answer`, `expected_context` (trích đúng đoạn trong corpus, kèm tên file hoặc Điều).

| Nhóm | Số câu | Ví dụ câu hỏi |
|---|---:|---|
| Đăng ký hộ kinh doanh | 3–4 | "Hồ sơ đăng ký hộ kinh doanh gồm những gì?", "Nộp hồ sơ ở đâu, bao lâu có giấy?" |
| Thuế | 4–5 | "Doanh thu bao nhiêu một năm thì hộ kinh doanh không phải nộp thuế?", "Tỷ lệ thuế GTGT và TNCN với ngành ăn uống là bao nhiêu?" |
| Hoá đơn | 2–3 | "Hộ kinh doanh nào phải dùng hoá đơn điện tử từ máy tính tiền?" |
| Thương mại điện tử | 2–3 | "Bán hàng trên sàn TMĐT thì ai khấu trừ và nộp thuế thay?" |
| Tra cứu bằng số hiệu (thử BM25) | 2 | "Thông tư 40/2021/TT-BTC quy định về nội dung gì?" |
| Kết hợp nhiều nguồn | 2 | Câu cần cả văn bản luật và bài hướng dẫn |

**Query dùng để calibrate threshold và demo refusal (để riêng, không đưa vào 15 câu):**
- Ngoài domain: "Thủ tục ly hôn thuận tình?", "Giá vàng hôm nay?", "Cách nấu phở bò?"
- Sát domain nhưng ngoài phạm vi: "Thủ tục thành lập công ty cổ phần?", "Thuế thu nhập doanh nghiệp của công ty TNHH?"

---

## 6. Phân công và checklist

### 👤 Người A — Data, PageIndex, Golden dataset (Task 1, 2, 3, 8)

- [ ] Xác minh danh sách văn bản ở 2.1: số hiệu, hiệu lực, văn bản sửa đổi mới nhất
- [ ] **Task 1:** tải ≥3 (nên 4–6) PDF/DOCX (>1KB) vào `data/landing/legal/`, đặt tên không dấu như `tt-40-2021-thue-ho-kinh-doanh.pdf`; hoàn thiện `download_documents()` với dict tên file → URL gốc
- [ ] **Task 2:** điền ≥5 (nên 6–8) URL vào `ARTICLE_URLS`, crawl bằng Crawl4AI (chạy `python -m playwright install chromium` trước); JSON đủ `url`, `title`, `date_crawled`, `content_markdown`; lọc bớt menu/quảng cáo trong markdown
- [ ] Lập **bảng nguồn** (2.3) và đưa vào README
- [ ] **Task 3:** convert PDF/DOCX bằng MarkItDown; kiểm tra PDF scan (không có text layer) thì đổi văn bản khác hoặc OCR; mỗi file ≥200 ký tự; chạy lại không sinh file trùng
- [ ] Header cho **mọi** file `.md`: `# Tên văn bản`, `**Source:** <URL>`, `**Số hiệu:**`, `**Ngày ban hành:**`, `**Hiệu lực:**` (news thì dùng ngày đăng và ngày crawl)
- [ ] Kiểm tra Markdown: dấu tiếng Việt, "Điều X" nằm đầu dòng, bảng tỷ lệ thuế không vỡ
- [ ] **Task 8:** `upload_documents()` lên PageIndex (convert `.md` → PDF bằng `fpdf2` nếu cần, **nhúng font Unicode** để không lỗi dấu); cache doc_id vào `pageindex_doc_ids.json` (file này đã có trong `.gitignore`); `pageindex_search()` trả `retrieval_method="pageindex"`, có timeout và try/except
- [ ] **Golden dataset** theo mục 5 (≥15 câu, phủ đủ các nhóm) và danh sách query calibrate
- [ ] Pass `test_corpus_*`, `test_standardized_*`, `test_golden_dataset_*`

### 👤 Người B — Indexing & Hybrid retrieval (Task 4, 5, 6, 7) + Threshold

- [x] Chốt embedding: OpenAI `text-embedding-3-small`; `.env.example` đã cập nhật
- [ ] **Task 4:**
  - [ ] `embed_texts()` dispatch theo `EMBEDDING_PROVIDER`, lazy-load model, embed theo batch
  - [ ] `get_collection()` dùng cosine
  - [ ] `load_documents()` parse header (title, url, số hiệu, ngày) ra metadata
  - [ ] `chunk_documents()` tách theo Điều trước rồi recursive (mục 4.1); ID ổn định `"{doc_id}::chunk-{i}"`; có `chunk_index`
  - [ ] `index_to_vectorstore()` dùng upsert, chạy lại không tạo bản trùng
- [ ] Ghi lý do chọn `CHUNK_SIZE`/`CHUNK_OVERLAP` và chunk theo Điều; nếu kịp thì so sánh với recursive thuần
- [ ] **Task 5:** `semantic_search()` với score = `1 - distance`, sort giảm dần, trả tối đa `top_k`
- [ ] **Task 6:** BM25 trên cùng corpus chunk; tokenizer theo mục 4.2 (giữ số hiệu văn bản); bỏ kết quả score ≤0
- [ ] **Task 7:** RRF `sum(1/(k+rank))` với rank từ 1, dedupe theo ID, gắn `retrieval_method="hybrid"`
- [ ] **Calibrate `SCORE_THRESHOLD`:** chạy dense trên golden questions và query ngoài/sát domain (mục 5); vẽ hoặc lập bảng phân bố best score; chọn ngưỡng tách được hai nhóm; ghi vào `.env` và RESULT.md
- [ ] Chuẩn bị ví dụ demo: truy vấn bằng số hiệu thì BM25 thắng, câu hỏi diễn đạt tự nhiên thì dense thắng, RRF lấy được cả hai
- [ ] *(Bonus +3)* Reranker (Jina hoặc BGE-reranker-v2-m3, hỗ trợ tiếng Việt), so sánh metric với RRF
- [ ] Pass `test_chunk_documents_*`, `test_semantic_*`, `test_lexical_*`, `test_rrf_*`

### 👤 Người C — Pipeline, Generation, UI, Evaluation (Task 9, 10, app.py, RESULT.md)

- [ ] Sửa đường dẫn RESULT.md và link README (mục 3.1); thêm `chroma_db/` vào `.gitignore`; sửa docstring `src/__init__.py` thành "Pháp luật cho hộ kinh doanh"
- [ ] **Task 9:** `retrieve()` lấy dense và sparse với `top_k*2` → RRF một lần → so threshold với **dense cosine gốc** → nếu thấp thì gọi PageIndex; fallback lỗi thì trả hybrid; `use_reranking=False` trả dense-only
- [ ] **Task 10:**
  - [ ] `reorder_for_llm()` không mutate list gốc
  - [ ] `format_context()` ghi `[Document n | Title | Số hiệu | Điều | Source]`
  - [ ] `call_llm()` có 3 nhánh OpenAI / Gemini / Anthropic theo `LLM_PROVIDER`
  - [ ] `SYSTEM_PROMPT` theo mục 4.3: citation `[Document n]`, nêu văn bản/Điều, ưu tiên văn bản mới hơn khi mâu thuẫn, kèm disclaimer
  - [ ] Safe refusal khi không có chunk hoặc provider lỗi: `sources=[]`, `retrieval_source="none"`
  - [ ] Kiểm tra citation: mọi `[Document n]` phải có `n ≤ len(sources)`
  - [ ] Tách `_generate(query, top_k, use_reranking)` cho A/B; map `dense` → `hybrid` (mục 3.6)
  - [ ] Không hard-code API key
- [ ] **app.py:** tiêu đề và mô tả theo đề tài; sidebar có disclaimer và 3–4 câu hỏi mẫu; hiển thị answer và sources (tên văn bản, số hiệu, Điều, url, score, retrieval_method) trong expander; lưu vào `session_state`; bắt lỗi để UI không crash
- [ ] **Script eval** `group_project/evaluation/run_eval.py`: RAGAS 4 metric (faithfulness, answer relevance, context recall, context precision) cho Config A (dense-only) và Config B (hybrid + RRF), giữ nguyên generator, evaluator, prompt, top_k
- [ ] Đo latency trung bình mỗi query (và token/cost nếu có) cho từng config
- [ ] Lưu output thô (CSV/JSON theo từng câu) vào `group_project/evaluation/`
- [ ] Điền **RESULT.md** không còn `TODO`: run info, scores, A/B, 3 worst performers (failure stage, root cause), recommendations; bảng Bonus experiments ghi `N/A` nếu không làm bonus
- [ ] *(Bonus +2)* Conversation memory, ví dụ "Còn nếu bán online thì sao?" sau câu hỏi về thuế
- [ ] *(Bonus +2)* Highlight đoạn Điều/Khoản được trích trong UI, hoặc deploy Streamlit Community Cloud
- [ ] Pass `test_reorder_*`, `test_retrieve_*`, `test_generation_*`, `test_evaluation_report_*`

### 👥 Việc chung cả nhóm

- [ ] Setup môi trường và `.env` (không commit); mỗi người làm trên branch riêng, merge qua PR
- [ ] Ghi lại commit/PR mình làm ngay trong lúc làm, để viết `reports/<mã-sv>-<tên>.md` theo [../reports/INDIVIDUAL_REPORT.md](../reports/INDIVIDUAL_REPORT.md)
- [ ] Phân tích worst performers: A xem data (thiếu văn bản, PDF lỗi, văn bản hết hiệu lực), B xem retrieval (chunk cắt ngang Điều, BM25 tách sai số hiệu), C xem generation (bịa, thiếu citation)
- [ ] README chạy lại được từ đầu: đề tài, bảng nguồn, cấu hình `.env`, lệnh Task 1 → 10, lệnh chạy eval và app
- [ ] Clone sạch và chạy lại trên máy thành viên khác
- [ ] `pytest -q` pass; repo không chứa `.env`, `chroma_db/`, `*.egg-info`, cache
- [ ] *(Bonus +3, chưa có người nhận — A hoặc B nhận nếu còn thời gian)* Query expansion: mở rộng từ viết tắt và đồng nghĩa ("HKD", "thuế khoán", "kê khai") hoặc HyDE, có A/B chứng minh

---

## 7. Đối chiếu rubric

| Hạng mục | Điểm | Phụ trách | Evidence khi chấm |
|---|---:|---|---|
| Dữ liệu có nguồn rõ ràng, chuẩn hoá | 10 | A | `data/`, bảng nguồn có số hiệu, hiệu lực, URL |
| Chunking, embedding, vector DB | 10 | B | Chunk theo Điều, lý do chọn tham số, index chạy lại không trùng |
| Dense, BM25, RRF | 20 | B | Task 5–7, test, ví dụ số hiệu (BM25) và câu tự nhiên (dense) |
| Retrieval pipeline + fallback | 10 | C (+A Task 8, B threshold) | Bảng calibrate, demo query ngoài/sát domain |
| Generation có citation + safe refusal | 15 | C | Citation văn bản/Điều map về `sources`, demo refusal, disclaimer |
| Chatbot end-to-end | 10 | C | `streamlit run app.py` |
| Golden dataset, 4 metric, A/B, phân tích lỗi | 10 | A + C + cả nhóm | `golden_dataset.json`, `run_eval.py`, `RESULT.md` |
| README, chạy lại được, individual reports | 5 | Cả nhóm | README, `reports/*.md` |
| Bonus query expansion / HyDE | +3 | Chưa có người nhận | Bonus experiments |
| Bonus reranker | +3 | B | So sánh với RRF |
| Bonus conversation memory | +2 | C | Demo follow-up |
| Bonus deploy / highlight citation | +2 | C | URL hoặc UI |

---

## 8. Thứ tự làm

| Giai đoạn | Người A | Người B | Người C |
|---|---|---|---|
| **Song song ngay** | Xác minh văn bản, thu thập data (Task 1–3) | Task 4–7 theo contract test (mock) | Task 9–10, app.py theo contract test (mock), sửa đường dẫn |
| **Khi có data** | Golden dataset, Task 8 | Index thật, calibrate threshold | End-to-end, viết `run_eval.py` |
| **Cuối** | Phân tích lỗi phía data | Bonus reranker | Chạy A/B, điền RESULT.md |

Contract test dùng mock, nên B và C bắt đầu code được ngay mà không phải chờ data.

### Kịch bản demo

1. **Câu đúng domain:** "Doanh thu bao nhiêu thì hộ kinh doanh phải nộp thuế?" → câu trả lời có citation tới văn bản/Điều, sources hiển thị `hybrid`.
2. **Tra bằng số hiệu:** "Nghị định 123/2020 quy định gì về hoá đơn?" → cho thấy BM25 góp phần.
3. **Ngoài domain:** "Thủ tục ly hôn?" → fallback hoặc safe refusal.
4. **Kết quả A/B:** bảng dense-only và hybrid trong RESULT.md.

## 9. Lệnh kiểm tra

```bash
pytest tests/test_contracts.py -q     # contract (không cần data/API)
pytest tests/test_acceptance.py -q    # data, golden dataset, RESULT.md
pytest -q                             # toàn bộ
streamlit run app.py                  # chạy chatbot
```
