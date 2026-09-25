# Hướng dẫn phần B — Indexing & Hybrid retrieval

**Người phụ trách:** Nguyễn Hải Nam (Leader)
**Phạm vi:** Task 4 (chunk, embed, ChromaDB), Task 5 (dense), Task 6 (BM25), Task 7 (RRF), calibrate `SCORE_THRESHOLD`, bonus reranker
**Liên quan rubric:** Chunking/embedding/vector DB **10đ**, Dense + BM25 + RRF **20đ**, một phần Retrieval + fallback **10đ**, bonus reranker **+3đ**

---

## 0. Phần B nằm ở đâu trong pipeline

```
[A] data/standardized/*.md
          │
   Task 4 ─ load_documents → chunk_documents → embed_chunks → index_to_vectorstore → chroma_db/
          │                                         ▲
          │                                  embed_texts() dùng chung
          ├── Task 5 semantic_search ───────────────┘   (score = cosine gốc)
          ├── Task 6 lexical_search  (BM25 trên cùng corpus chunk)
          └── Task 7 rerank_rrf([dense, bm25])  →  [C] Task 9 retrieve()
```

- **Đầu vào của B:** các file Markdown do A sinh ra trong `data/standardized/legal/` và `data/standardized/news/`.
- **Đầu ra B giao cho C:** 3 hàm `semantic_search`, `lexical_search`, `rerank_rrf` đúng contract, cùng giá trị `SCORE_THRESHOLD` đã calibrate.

---

## 1. Trạng thái hiện tại

Code của Task 4–7 **đã viết xong và đã test**. Dependencies đã cài trong `.venv`. Việc còn lại là chốt embedding, chờ data của A, index thật, calibrate threshold, lấy evidence và commit.

| File | Nội dung chính | Trạng thái |
|---|---|---|
| `src/task4_chunking_indexing.py` | Dispatch embedding (`sentence_transformers`/`openai`/`gemini`), parse header, chunk theo Điều, gắn tên văn bản vào đầu mỗi chunk, upsert có xoá chunk cũ | ✅ Contract test + smoke test |
| `src/task5_semantic_search.py` | score = `1 - distance`, khôi phục `url=None` | ✅ Contract test + smoke test |
| `src/task6_lexical_search.py` | Tokenizer giữ số hiệu, IDF luôn dương, lazy-load corpus từ Chroma | ✅ Contract test + smoke test |
| `src/task7_reranking.py` | RRF không mutate input; chạy trực tiếp in ra kết quả đến từ dense hay bm25 | ✅ Contract test + smoke test |
| `src/calibrate_threshold.py` | So best dense score giữa câu trong domain và ngoài domain, đề xuất threshold | Đã code, cần data |
| `.env.example` | Thêm `EMBEDDING_DIM` | Xong |

**Kết quả test (25/09/2026):**
- `pytest tests/test_contracts.py`: **11 passed, 4 failed**. 4 test fail đều thuộc Task 9–10 (phần C, chưa code).
- Smoke test với Chroma thật (data giả, embedding giả) đã xác nhận:
  - Header được parse đúng.
  - Chunk được chia theo Điều; dòng bị ngắt giữa câu "Điều 4 của Thông tư này…" không bị tách nhầm thành Điều mới.
  - Index 2 lần vẫn giữ nguyên số chunk; khi index lại ra ít chunk hơn thì chunk thừa bị xoá.
  - `url` được khôi phục sau khi đọc từ Chroma.
  - BM25 khớp số hiệu trên mọi chunk của văn bản.
  - Output của dense, BM25 và RRF đều đúng contract.

**Bạn cần đọc hiểu code trước buổi demo:** giảng viên sẽ hỏi vì sao chọn cách làm này. Các quyết định quan trọng được giải thích ở mục 7.

---

## 2. Setup môi trường

```powershell
# Windows PowerShell, tại thư mục repo
.venv\Scripts\activate
python -m pip install -e ".[dev]"
copy .env.example .env      # nếu chưa có .env
```

### 2.1. Embedding: đã chốt **OpenAI `text-embedding-3-small`** (1536 chiều)

- **Lý do chọn:** nhẹ máy (không phải tải model khoảng 2GB như bge-m3), nhanh, rẻ (corpus vài trăm chunk chỉ tốn khoảng vài cent), hỗ trợ tiếng Việt tốt. Cùng provider với LLM mặc định (`LLM_PROVIDER=openai`) nên cả nhóm chỉ cần một key.
- **Trade-off (ghi vào report):** tốn phí mỗi lần index và eval, và phụ thuộc mạng. Không chạy offline được như bge-m3.
- **Đã cấu hình** trong `.env` và `.env.example`: `EMBEDDING_PROVIDER=openai`, `EMBEDDING_MODEL=text-embedding-3-small`. `EMBEDDING_DIM` để trống (tự suy ra 1536).
- **Bạn cần làm:** điền `OPENAI_API_KEY=sk-...` vào `.env` (không commit). Báo A và C dùng cùng cấu hình này.
- `pyproject.toml` giữ nguyên dòng `sentence-transformers` bị comment, vì không cần nữa.

> ⚠️ **Cả nhóm phải dùng cùng một model.** Đổi model thì phải xoá `chroma_db/` rồi index lại. Code sẽ báo lỗi nếu phát hiện collection được index bằng model khác.

Kiểm tra embedding chạy được:

```powershell
python -c "from src.task4_chunking_indexing import embed_texts; v=embed_texts(['hộ kinh doanh nộp thuế']); print(len(v[0]))"
# Kết quả mong đợi: 1536
```

---

## 3. Bước 1 — Chạy contract test (không cần data)

```powershell
pytest tests/test_contracts.py -q
```

Các test thuộc phần B **phải pass**:

| Test | Kiểm tra gì |
|---|---|
| `test_public_function_signatures_are_stable` | Signature `load_documents()`, `chunk_documents(documents)`, `semantic_search(query, top_k)`, `lexical_search(query, top_k)` |
| `test_chunk_documents_preserves_identity_and_metadata` | ID duy nhất, `chunk_index` liên tục từ 0, giữ `source`, độ dài chunk ≤ `CHUNK_SIZE * 1.1` |
| `test_semantic_search_uses_shared_embedding_and_contract` | Dùng `embed_texts` và `get_collection` của Task 4, output đúng SearchResult |
| `test_lexical_search_returns_bm25_contract` | `retrieval_method="bm25"`, chunk liên quan nhất đứng đầu |
| `test_rrf_uses_rank_deduplicates_and_marks_hybrid` | Score = `1/62 + 1/61`, dedupe, `retrieval_method="hybrid"` |

Các test của Task 9–10 (phần C) sẽ fail với `NotImplementedError` cho tới khi C code xong. Đó là bình thường. Nếu chỉ muốn chạy test của phần B:

```powershell
pytest tests/test_contracts.py -q -k "signature or chunk or semantic or lexical or rrf or validator"
```

> Test signature import luôn cả Task 8–10. Các file đó hiện chỉ `raise` khi gọi hàm chứ không raise lúc import, nên test vẫn pass.

---

## 4. Bước 2 — Index dữ liệu thật (sau khi A có data)

### 4.1. Kiểm tra đầu vào từ A

```powershell
dir data\standardized\legal, data\standardized\news
```

Mỗi file `.md` nên có header dạng dưới đây (đã thống nhất trong TEAM_PLAN). Code đọc các trường này ra metadata:

```markdown
# Thông tư 40/2021/TT-BTC hướng dẫn thuế GTGT, TNCN đối với hộ, cá nhân kinh doanh

**Source:** https://...
**Số hiệu:** 40/2021/TT-BTC
**Ngày ban hành:** 01/06/2021
**Hiệu lực:** 01/08/2021

---

Nội dung...
```

Các key được nhận diện (trong `_HEADER_FIELDS`): `Source`, `URL`, `Số hiệu`, `Ngày ban hành`, `Hiệu lực`, `Ngày đăng`, `Crawled`. Nếu A dùng tên key khác thì thêm vào dict này.

### 4.2. Kiểm tra chunking trước khi embed (nhanh, không tốn tiền)

```powershell
python -c "from src.task4_chunking_indexing import *; d=load_documents(); c=chunk_documents(d); print(len(d),'docs',len(c),'chunks'); [print(x['id'], x['metadata'].get('article'), len(x['content'])) for x in c[:15]]"
```

Những gì cần soi:
- [ ] Mỗi văn bản luật có `article` (ví dụ `Điều 4. ...`) ở phần lớn chunk. Nếu toàn `None`, MarkItDown đã làm mất format "Điều N." và cần chỉnh regex `_ARTICLE_HEADING`.
- [ ] Không có chunk quá ngắn vô nghĩa (chỉ vài ký tự, số trang, header/footer PDF). Nếu có, báo A làm sạch ở Task 3.
- [ ] `title` và `url` đúng (không phải tên file) với cả legal lẫn news.
- [ ] Tổng số chunk hợp lý: khoảng 20–100 chunk mỗi văn bản luật, 3–15 chunk mỗi bài báo.

In thử một văn bản luật để xem có bị cắt ngang giữa Điều không:

```powershell
python -c "from src.task4_chunking_indexing import *; c=[x for x in chunk_documents(load_documents()) if x['metadata']['doc_type']=='legal']; [print('=====',x['id'],'\n',x['content'][:300]) for x in c[5:10]]"
```

### 4.3. Index

```powershell
python -m src.task4_chunking_indexing
# Indexed N chunks from M documents (provider/model, legal_article+recursive)
```

Chạy lại **lần thứ hai** để chứng minh không tạo dữ liệu trùng:

```powershell
python -m src.task4_chunking_indexing
python -c "from src.task4_chunking_indexing import get_collection; print(get_collection().count())"
# count phải bằng N, không phải 2N
```

---

## 5. Bước 3 — Thử search và lấy ví dụ demo

```powershell
python -m src.task5_semantic_search "Doanh thu bao nhiêu thì hộ kinh doanh phải nộp thuế?"
python -m src.task6_lexical_search "Thông tư 40/2021/TT-BTC"
python -m src.task7_reranking "Nghị định 123/2020 quy định gì về hoá đơn?"
```

Output của Task 7 có dạng `0.03252  [dense+bm25]  legal/nd-123-2020.md::chunk-12`, cho biết mỗi kết quả do phương pháp nào tìm thấy.

**Cần thu thập 3 ví dụ cho demo và báo cáo (rubric Dense/BM25/RRF, 20đ):**

| Loại | Query gợi ý | Kỳ vọng |
|---|---|---|
| BM25 thắng | Query chứa số hiệu: `"Thông tư 40/2021/TT-BTC"`, `"Nghị định 123/2020"` | BM25 top-1 đúng văn bản; dense có thể lẫn sang văn bản khác |
| Dense thắng | Query diễn đạt tự nhiên, không trùng từ: `"bán đồ trên mạng có phải đóng thuế không"` | Dense tìm được chunk về TMĐT; BM25 yếu vì văn bản dùng từ "thương mại điện tử" |
| RRF có lợi | Query kết hợp: `"hộ kinh doanh bán online theo Nghị định 117/2025 nộp thuế thế nào"` | Top-5 hybrid có chunk từ cả hai nguồn (`[dense+bm25]`, `[dense]`, `[bm25]`) |

Chụp màn hình hoặc copy output vào ghi chú để đưa vào individual report.

---

## 6. Bước 4 — Calibrate `SCORE_THRESHOLD`

**Điều kiện:** A đã có `golden_dataset.json` (≥15 câu) và đã index xong.

```powershell
python -m src.calibrate_threshold
```

Script sẽ:
1. Lấy best dense cosine score của từng câu golden (trong domain) và 6 câu ngoài hoặc sát domain (danh sách `OUT_OF_DOMAIN_QUERIES`).
2. In bảng sắp theo score và đánh dấu `<-- sai phía` với câu bị phân loại sai.
3. Đề xuất ngưỡng có accuracy cao nhất và lưu vào `group_project/evaluation/threshold_calibration.json`.

**Cách đọc kết quả:**
- Hai nhóm tách rõ (in-domain min > out-domain max): lấy ngưỡng đề xuất.
- Hai nhóm chồng lấn: ưu tiên **không fallback nhầm** câu trong domain, tức là chọn ngưỡng thấp hơn một chút. Câu sát domain (công ty TNHH) lọt qua thì vẫn còn prompt của C từ chối được.
- Mức tham khảo: với bge-m3, câu trong domain thường khoảng 0.55–0.75, câu ngoài domain khoảng 0.3–0.45. OpenAI small thường thấp hơn. **Đừng dùng số tham khảo này, hãy dùng số đo được.**

**Sau khi có số:**
- [ ] Ghi vào `.env`: `SCORE_THRESHOLD=0.xx`
- [ ] Báo C để Task 9 đọc `SCORE_THRESHOLD` từ env (hiện `task9` đang hard-code `0.3`)
- [ ] Gửi C nội dung dòng "Fallback threshold and calibration" cho `RESULT.md`, ví dụ: `0.48 — calibrate trên 15 câu in-domain + 6 câu out-domain, accuracy 95%, xem threshold_calibration.json`
- [ ] Commit file `threshold_calibration.json` làm evidence

---

## 7. Các quyết định kỹ thuật (để giải thích khi demo và viết report)

Report cá nhân chỉ cần **2 quyết định**. Nên chọn quyết định 1 và 2 dưới đây.

### Quyết định 1 — Chunk theo Điều thay vì cắt theo số ký tự
- **Lý do:** mỗi Điều trong văn bản luật là một đơn vị ý nghĩa trọn vẹn. Cắt thuần theo ký tự dễ chặt đôi một Khoản, khiến chunk mất ngữ cảnh "đây là Điều gì".
- **Cách làm:** regex `^Điều N.` tách thành từng Điều; Điều nào dài hơn 800 ký tự thì cắt tiếp bằng recursive splitter và **lặp lại tiêu đề Điều** ở đầu mỗi chunk con. Metadata `article` giúp C hiển thị citation "Điều 4".
- **Gắn tên văn bản vào đầu mỗi chunk (contextual chunk header):** số hiệu "40/2021/TT-BTC" chỉ xuất hiện ở trang đầu. Nếu không gắn, chunk "Điều 7" sẽ không chứa số hiệu, BM25 không khớp query theo số hiệu, còn dense không biết chunk thuộc văn bản nào. Smoke test cho thấy: chưa gắn thì query "Thông tư 40/2021" chỉ khớp 1/5 chunk (nhờ chữ "Thông tư"); gắn rồi thì khớp cả 5.
- **Trade-off:** phụ thuộc format "Điều N." còn nguyên sau MarkItDown. PDF lỗi format sẽ rơi về recursive thuần. Các Điều rất ngắn tạo ra chunk nhỏ.
- **Evidence nên có:** so sánh context recall hoặc precision giữa chunk theo Điều và recursive thuần (đổi hàm `_chunk_texts` rồi eval lại) nếu kịp.

### Quyết định 2 — Tokenizer BM25 giữ số hiệu văn bản, IDF luôn dương
- **Lý do:** người dùng hay hỏi theo số hiệu ("Thông tư 40/2021"). Tokenizer `split()` mặc định vẫn giữ được số hiệu nhưng dính dấu câu ("40/2021/tt-btc," khác "40/2021/tt-btc"). Tokenizer bằng regex giữ `123/2020/nđ-cp` thành một token **và** thêm các phần `123`, `2020`, `nđ`, `cp`, nên query viết tắt "123/2020" vẫn khớp.
- **IDF:** `BM25Okapi` gốc cho IDF = 0 khi một từ xuất hiện ở đúng nửa corpus, và âm khi nhiều hơn. Với corpus nhỏ, điều này làm mọi score bằng 0 (chính test contract với 2 chunk sẽ fail). Công thức kiểu Lucene `log(1 + (N−n+0.5)/(n+0.5))` luôn dương.
- **Trade-off:** chưa tách từ ghép tiếng Việt ("hộ kinh doanh" thành 3 token rời). Có thể thử `pyvi`/`underthesea` rồi so sánh.

### Các quyết định khác (nêu miệng khi được hỏi)
- **Score dense = cosine gốc, không chuẩn hoá:** Task 9 dùng score này để quyết định fallback. Score RRF chỉ phản ánh thứ hạng (khoảng 0.016–0.033), không so với threshold được.
- **RRF chỉ gộp theo rank:** cosine (0–1) và BM25 (0–20+) khác thang đo nên không cộng trực tiếp được. k=60 là giá trị chuẩn trong bài báo gốc về RRF.
- **Chunk ID ổn định `"{đường dẫn file}::chunk-{i}"` + upsert + xoá chunk cũ:** index lại không trùng. Nếu một văn bản sinh ít chunk hơn lần trước, các chunk thừa sẽ bị xoá.
- **Lưu tên model vào metadata collection:** tránh lỗi âm thầm khi một thành viên index bằng model khác (sai số chiều hoặc vector vô nghĩa).
- **`CHUNK_SIZE=800`, `OVERLAP=100`:** một Khoản dài khoảng 200–600 ký tự, nên một chunk chứa 1–3 Khoản. Top-5 chunk khoảng 4000 ký tự context, vừa với prompt.

---

## 8. Bonus reranker (+3đ, làm khi phần chính đã xong)

**Điều kiện được tính điểm:** chạy được **và** có so sánh metric với RRF trên cùng golden dataset.

Có 2 hướng:

| Hướng | Cài đặt | Ghi chú |
|---|---|---|
| **Jina Reranker API** (nhanh nhất) | `JINA_API_KEY` trong `.env`, gọi `POST https://api.jina.ai/v1/rerank` với model `jina-reranker-v2-base-multilingual` | Hỗ trợ tiếng Việt, có free tier |
| **BGE reranker local** | `pip install sentence-transformers`, dùng `CrossEncoder("BAAI/bge-reranker-v2-m3")` | Khoảng 2.2GB, chậm trên CPU |

Gợi ý cách làm:
1. Thêm hàm `rerank_cross_encoder(query, candidates, top_k)` vào `task7_reranking.py`. **Không đổi `rerank_rrf`.**
2. Luồng: RRF lấy top-20 → cross-encoder chấm lại → top-5. Gán `retrieval_method="hybrid"` và score mới (vẫn sort giảm dần).
3. Phối hợp với C: thêm cờ env (ví dụ `USE_CROSS_ENCODER=1`) để Task 9 bật/tắt, **không đổi signature `retrieve`**.
4. C chạy eval thêm Config C (hybrid + RRF + reranker), điền bảng "Bonus experiments" trong RESULT.md: metric delta và latency delta.

---

## 9. Phối hợp với A và C

| Với | Cần thống nhất | Khi nào |
|---|---|---|
| Cả nhóm | Embedding provider + model | **Ngay đầu buổi** |
| A | Format header Markdown (mục 4.1), đặc biệt `**Source:**` và dòng "Điều N." còn nguyên | Trước khi A chạy Task 3 |
| A | Dòng `# Title` phải chứa **loại văn bản + số hiệu** (ví dụ `# Thông tư 40/2021/TT-BTC hướng dẫn thuế…`), vì title được gắn vào đầu mọi chunk để BM25 khớp số hiệu | Trước khi A chạy Task 3 |
| A | Golden dataset xong thì báo để calibrate | Giữa buổi |
| A | Chunk rác (header/footer PDF, số trang) thì báo A làm sạch | Sau bước 4.2 |
| C | Giá trị `SCORE_THRESHOLD`, và Task 9 phải đọc từ env | Sau bước 6 |
| C | `rerank_rrf` gọi dạng `rerank_rrf([dense, sparse], top_k=...)`, không truyền `k=` (test mock `lambda lists, top_k`) | Khi C code Task 9 |
| C | Metadata chunk có thêm `article`, `doc_number`, `issued_date`, `effective_date` để C hiển thị citation | Khi C code Task 10 và app |

---

## 10. Git workflow

```powershell
git checkout -b feat/b-indexing-retrieval
git add src/task4_chunking_indexing.py src/task5_semantic_search.py src/task6_lexical_search.py src/task7_reranking.py src/calibrate_threshold.py .env.example
git commit -m "feat(task4-7): legal-aware chunking, dense/BM25 search, RRF"
git push -u origin feat/b-indexing-retrieval
# Tạo PR vào main, nhờ C review phần interface
```

- Chia commit nhỏ theo task (Task 4, Task 5–6, Task 7, calibrate). Report cá nhân yêu cầu dẫn commit/PR làm bằng chứng.
- **Không commit:** `.env`, `chroma_db/` (thêm vào `.gitignore` nếu C chưa thêm), `*.egg-info/`.
- Thay đổi `pyproject.toml` (sentence-transformers) nên commit riêng, kèm lý do.

---

## 11. Xử lý sự cố thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ModuleNotFoundError: sentence_transformers` | Dòng này đang bị comment trong `pyproject.toml` | `pip install sentence-transformers` hoặc chuyển sang provider OpenAI |
| `Collection đã index bằng X, hiện đang dùng Y` | Đổi model embedding | Xoá thư mục `chroma_db/` rồi index lại |
| `Collection expecting embedding with dimension of ...` | Tương tự trên (collection cũ) | Xoá `chroma_db/` |
| `... trả về N chiều, EMBEDDING_DIM=M` | Đặt sai `EMBEDDING_DIM` trong `.env` | Để trống hoặc sửa đúng số chiều |
| `lexical_search` trả `[]` | Chưa index (corpus rỗng) hoặc query toàn ký tự đặc biệt | Chạy Task 4 trước |
| BM25 dùng corpus cũ sau khi index lại | `CORPUS` được cache trong process | Khởi động lại Streamlit/Python |
| Tất cả chunk có `article=None` | PDF convert làm mất "Điều N." ở đầu dòng | Mở file `.md` xem format thật, chỉnh `_ARTICLE_HEADING` |
| Embed bge-m3 rất chậm | Chạy trên CPU | Bình thường (vài phút). Chỉ embed lại khi data đổi |
| `UnicodeEncodeError: 'charmap' codec…` khi in tiếng Việt | Console Windows dùng cp1252 (hay gặp khi pipe output) | Chạy `$env:PYTHONIOENCODING="utf-8"` trước lệnh `python` |
| OpenAI `RateLimitError` | Batch quá lớn hoặc tài khoản free | Giảm `EMBEDDING_BATCH_SIZE` |

---

## 12. Checklist tổng (đánh dấu khi xong)

**Setup**
- [x] Chốt embedding provider: OpenAI `text-embedding-3-small`, đã cập nhật `.env` và `.env.example`
- [ ] Điền `OPENAI_API_KEY` vào `.env`, báo cả nhóm dùng cùng model
- [ ] `embed_texts` trả đúng số chiều

**Code & test**
- [ ] 5 test contract của phần B pass
- [ ] Đọc hiểu toàn bộ code Task 4–7 (giải thích được từng quyết định ở mục 7)

**Dữ liệu thật**
- [ ] Soi chunking (mục 4.2): có `article`, không có chunk rác, title/url đúng
- [ ] Index thành công; index lần 2 không tăng `count()`
- [ ] 3 ví dụ demo: BM25 thắng, dense thắng, RRF gộp (mục 5)

**Threshold**
- [ ] Chạy `calibrate_threshold`, chọn ngưỡng, ghi `.env`
- [ ] Gửi số liệu cho C (Task 9 + RESULT.md), commit `threshold_calibration.json`

**Bàn giao & báo cáo**
- [ ] PR phần B merge vào main
- [ ] Hỗ trợ phân tích worst performers ở phía retrieval (chunk cắt sai, BM25 tách sai số hiệu, dense miss)
- [ ] Viết `reports/2A202602476-nam.md`: bảng phần việc (Task 4–7, calibrate) kèm commit/PR, 2 quyết định ở mục 7, query test và kết quả, 1 hạn chế (chưa tách từ tiếng Việt / phụ thuộc format "Điều N.")

**Bonus (nếu còn thời gian)**
- [ ] Reranker Jina/BGE + so sánh với RRF trong RESULT.md
