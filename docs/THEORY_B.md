# Lý thuyết phần B — Chunking, Embedding, Dense, BM25, RRF, Threshold

Tài liệu ôn tập cho phần B (Task 4–7 và calibrate threshold). Mỗi khái niệm gắn với code trong `src/task4`–`task7` và `src/calibrate_threshold.py`.

```
chunking → embedding → dense search (cosine) ─┐
                     → BM25 (từ khoá) ────────┴→ RRF → [C] retrieve() → threshold / fallback
```

---

## 1. Retrieval quyết định chất lượng RAG

RAG gồm 2 bước: **retrieve** (tìm đoạn văn liên quan) và **generate** (LLM trả lời dựa trên các đoạn đó). LLM chỉ trả lời tốt khi được đưa đúng đoạn cần thiết. Nếu retrieval bỏ sót đoạn chứa đáp án, LLM sẽ bịa hoặc phải từ chối.

Hai metric RAGAS phản ánh trực tiếp phần B:

- **Context recall:** những đoạn cần để trả lời có nằm trong top-k không.
- **Context precision:** trong top-k, các đoạn liên quan có được xếp lên đầu không.

---

## 2. Chunking — chia văn bản thành đoạn nhỏ

**Vì sao phải chia:**

- Embed cả văn bản 50 trang thành một vector sẽ trộn lẫn mọi chủ đề (vector bị "trung bình hoá"), nên không tìm chính xác được.
- LLM có giới hạn context, và nhồi quá nhiều text thì dễ bị lạc (hiện tượng *lost in the middle*).

**Trade-off về kích thước chunk:**

| Chunk nhỏ (~200 ký tự) | Chunk lớn (~2000 ký tự) |
|---|---|
| Vector sắc nét, precision cao | Đủ ngữ cảnh |
| Dễ mất ngữ cảnh ("mức này" là mức nào?) | Vector bị pha loãng, nhiều nhiễu |

**Lựa chọn trong code:** `CHUNK_SIZE = 800`, `CHUNK_OVERLAP = 100`. Một Khoản luật dài khoảng 200–600 ký tự, nên mỗi chunk chứa trọn 1–3 Khoản. **Overlap** là phần lặp lại giữa hai chunk liền nhau, để câu nằm ở ranh giới không bị mất nghĩa.

**Chunk theo cấu trúc (structure-aware):** splitter thông thường cắt theo số ký tự nên có thể chặt đôi một Điều. Văn bản luật có sẵn cấu trúc *Chương → Điều → Khoản*, và mỗi Điều là một đơn vị nghĩa trọn vẹn. Vì vậy code:

1. Tách theo regex `^Điều N.` (bắt buộc có dấu chấm, để không nhầm với dòng bị ngắt giữa câu như "Điều 4 của Luật này…").
2. Điều nào dài hơn chunk size thì cắt tiếp bằng `RecursiveCharacterTextSplitter`, và lặp lại tiêu đề Điều ở đầu mỗi chunk con.
3. Ghi metadata `article` (ví dụ "Điều 6. Tỷ lệ thuế…") để phần generation hiển thị citation theo Điều.

**Contextual chunk header:** chunk "Điều 6. Tỷ lệ thuế…" đứng riêng thì không biết thuộc văn bản nào. Gắn tên văn bản ("Thông tư 40/2021/TT-BTC…") vào đầu mọi chunk giúp:

- **Dense** biết chunk thuộc văn bản nào.
- **BM25** khớp được số hiệu, vốn chỉ xuất hiện ở trang đầu. Trong smoke test, số chunk khớp query "Thông tư 40/2021" tăng từ **1/5 lên 5/5**.

---

## 3. Embedding — biến text thành vector

Model embedding (`text-embedding-3-small`) biến mỗi đoạn text thành một **vector 1536 số thực**. Model được huấn luyện để các câu **cùng nghĩa** có vector **gần nhau**, kể cả khi không dùng chung từ nào:

```
"bán đồ trên mạng có phải đóng thuế không"   ─┐
                                              ├─ hai vector gần nhau
"thuế đối với hoạt động thương mại điện tử"  ─┘   (dù không trùng từ)
```

**Nguyên tắc bắt buộc:** query và chunk phải được embed bằng **cùng một model**. Vì vậy Task 5 gọi lại `embed_texts()` của Task 4. Vector của hai model khác nhau nằm trong hai "không gian" khác nhau, nên so sánh chúng là vô nghĩa. Code lưu tên model vào metadata của collection để phát hiện lỗi này.

---

## 4. Cosine similarity và vector database

**Cosine similarity** đo góc giữa hai vector:

```
cos(A, B) = (A · B) / (|A| × |B|)     ∈ [-1, 1]
```

- 1 nghĩa là cùng hướng (rất giống); 0 nghĩa là không liên quan.
- Cosine chỉ xét **hướng**, không xét độ dài vector, nên hợp để so nghĩa.

Chroma trả về **cosine distance = 1 − cos**, nên Task 5 đổi lại thành `score = 1 − distance`. Đây là **score gốc, có ý nghĩa tuyệt đối**: 0.7 là "khá giống", 0.2 là "gần như không liên quan". Nhờ vậy score này dùng làm threshold được (mục 8).

**Vector database (ChromaDB):** so query với hàng triệu vector từng cái một thì quá chậm. Chroma dùng **HNSW** (Hierarchical Navigable Small World), một cấu trúc đồ thị để tìm **gần đúng** các vector gần nhất (ANN — Approximate Nearest Neighbor), đổi một chút độ chính xác lấy tốc độ. Cấu hình `hnsw:space: cosine` cho Chroma biết dùng cosine làm thước đo.

**Upsert và ID ổn định:** ID như `legal/tt-40-2021.md::chunk-3` luôn cố định. Upsert với ID đã có sẽ **ghi đè** chứ không thêm mới, nên index lại không tạo bản trùng. Code còn xoá các chunk thừa khi một văn bản sinh ít chunk hơn lần trước.

**Chroma không lưu `None`:** metadata `url=None` bị bỏ khi index và được khôi phục khi đọc ra, để giữ đúng contract.

---

## 5. BM25 — tìm theo từ khoá

BM25 là thuật toán **lexical**: chấm điểm dựa trên **từ trùng khớp** giữa query và văn bản. Với mỗi từ q trong query:

```
score(D, Q) = Σ  IDF(q) × ────── f(q,D) × (k1 + 1) ──────
             q∈Q          f(q,D) + k1 × (1 − b + b × |D|/avgdl)
```

| Thành phần | Ý nghĩa | Trực giác |
|---|---|---|
| **TF** `f(q,D)` | Số lần từ q xuất hiện trong chunk D | Xuất hiện nhiều thì liên quan hơn, nhưng **bão hoà** nhờ `k1` (≈1.5): xuất hiện 20 lần không có giá trị gấp 20 lần xuất hiện 1 lần |
| **IDF** `IDF(q)` | Độ hiếm của từ trong corpus | "123/2020/nđ-cp" hiếm nên điểm cao; "hộ", "kinh", "doanh" có ở mọi chunk nên điểm gần 0 |
| **Chuẩn hoá độ dài** `b` (≈0.75) | So độ dài chunk với độ dài trung bình `avgdl` | Chunk dài tự nhiên chứa nhiều từ hơn, nên bị trừ bớt cho công bằng |

**Vì sao sửa IDF:** IDF gốc của `BM25Okapi` là `log((N − n + 0.5) / (n + 0.5))`, với N là số chunk và n là số chunk chứa từ.

- Corpus 2 chunk, từ xuất hiện ở 1 chunk: `log(1.5 / 1.5) = 0`, mọi score bằng 0. Contract test với 2 chunk sẽ fail.
- Từ xuất hiện ở hơn nửa corpus thì IDF **âm**.

Công thức kiểu Lucene `log(1 + (N − n + 0.5) / (n + 0.5))` luôn dương.

**Tokenizer:** BM25 chỉ tốt khi tách từ đúng. Code chuẩn hoá lowercase và Unicode NFC, giữ `123/2020/nđ-cp` thành một token, **và** thêm các phần con `123`, `2020`, `nđ`, `cp`, nên query "Nghị định 123/2020" vẫn khớp.

**Điểm yếu:**

- Score BM25 **không có thang đo cố định** (có thể là 3.2 hay 15.7 tuỳ corpus và query), nên không so sánh được giữa các query.
- Chưa tách từ ghép tiếng Việt: "hộ kinh doanh" thành 3 token rời. Có thể cải thiện bằng `pyvi` hoặc `underthesea`.

---

## 6. Vì sao cần hybrid (dense + BM25)

| Loại query | Dense | BM25 |
|---|---|---|
| "Thông tư 40/2021/TT-BTC quy định gì?" | ❌ Số hiệu chỉ là chuỗi ký tự, embedding không hiểu rõ | ✅ Khớp chính xác token hiếm |
| "bán đồ trên mạng có phải đóng thuế không" | ✅ Hiểu "trên mạng" ≈ "thương mại điện tử" | ❌ Văn bản không dùng từ "trên mạng" |
| Tên riêng, mã số, con số ("100 triệu") | Yếu | Mạnh |
| Diễn đạt khác, đồng nghĩa | Mạnh | Yếu |

Hai phương pháp **bù điểm yếu cho nhau**. Hybrid lấy kết quả của cả hai rồi gộp lại, và điều này thể hiện ở context recall cao hơn trong so sánh A/B (Config A dense-only và Config B hybrid + RRF).

---

## 7. RRF (Reciprocal Rank Fusion) — gộp hai bảng xếp hạng

**Vấn đề:** cosine nằm trong [0, 1], còn BM25 nằm trong [0, 20+]. Cộng thẳng thì BM25 lấn át. Chuẩn hoá min-max cũng không ổn vì phụ thuộc từng query.

**Giải pháp:** bỏ qua score, **chỉ dùng thứ hạng**:

```
RRF(d) = Σ   1 / (k + rank_i(d))       với k = 60, rank bắt đầu từ 1
         i
```

**Ví dụ (chính là contract test):**

| Chunk | Hạng dense | Hạng BM25 | RRF |
|---|---|---|---|
| chunk-0 | 1 | — | 1/61 = 0.01639 |
| chunk-1 | 2 | 1 | 1/62 + 1/61 = **0.03252** ← hạng 1 |
| chunk-2 | — | 2 | 1/62 = 0.01613 |

chunk-1 thắng dù không đứng đầu danh sách nào, vì **cả hai phương pháp đều cho là liên quan**. Tài liệu được nhiều nguồn đồng thuận thì đáng tin hơn. Đây là ý tưởng cốt lõi của RRF.

**Vai trò của k = 60** (giá trị chuẩn trong bài báo gốc của Cormack và cộng sự, 2009):

- k lớn làm khoảng cách giữa hạng 1 và hạng 10 nhỏ lại (1/61 so với 1/70), tức là "dân chủ" hơn.
- k nhỏ làm hạng đầu áp đảo.

**Các quy tắc trong code:**

- Một ID chỉ được tính **một lần trong mỗi danh sách**.
- Không sửa (mutate) danh sách đầu vào.
- Kết quả gắn `retrieval_method="hybrid"`.
- **Chỉ fuse một lần.** Fuse lại kết quả đã fuse sẽ làm méo rank; contract test kiểm tra điều này.

---

## 8. Threshold và fallback

Task 9 cần quyết định: *câu hỏi này corpus có trả lời được không?* Nếu best score thấp, câu hỏi có thể nằm ngoài phạm vi, và pipeline chuyển sang PageIndex hoặc từ chối.

**Vì sao dùng cosine gốc mà không dùng RRF score:**

- RRF score luôn nằm trong khoảng 0.016–0.033 **bất kể query có liên quan hay không**: hạng 1 luôn được 1/61. RRF chỉ biết thứ tự, không biết "giỏi đến đâu".
- Cosine là thước đo **tuyệt đối**: "giá vàng hôm nay" sẽ có best cosine thấp thật sự.

**Calibrate là bài toán phân loại nhị phân** trên một đặc trưng duy nhất (best cosine):

```
in-domain:   0.62  0.58  0.71  0.55 ...  →  nên ≥ threshold
out-domain:  0.31  0.28  0.44  0.35 ...  →  nên < threshold
                          ↑ chọn điểm cắt có accuracy cao nhất
```

`src/calibrate_threshold.py` thử mọi điểm cắt nằm giữa các score đã đo, chọn điểm có accuracy cao nhất, rồi lưu evidence vào `group_project/evaluation/threshold_calibration.json`.

**Trade-off khi hai nhóm chồng lấn:**

- **Threshold cao:** câu hợp lệ bị fallback nhầm, người dùng mất câu trả lời đúng.
- **Threshold thấp:** câu ngoài domain lọt qua, nhưng vẫn còn prompt của LLM làm lớp chặn thứ hai để từ chối.

Nên ưu tiên threshold **hơi thấp**. Không có con số đúng cho mọi hệ thống: threshold phụ thuộc model embedding và corpus, nên phải đo.

---

## 9. Câu hỏi thường gặp khi demo

| Câu hỏi | Trả lời ngắn |
|---|---|
| Vì sao không cộng thẳng cosine với BM25? | Khác thang đo, BM25 không có giới hạn trên. RRF chỉ dùng rank nên không phụ thuộc thang đo |
| Vì sao fallback dùng cosine mà không dùng RRF score? | RRF chỉ phản ánh thứ tự, hạng 1 luôn được 1/61; cosine mới đo độ liên quan tuyệt đối |
| Vì sao Task 4 và Task 5 phải dùng chung model embedding? | Vector của hai model nằm trong hai không gian khác nhau, không so được |
| Chunk size 800 dựa trên gì? | Độ dài một Khoản luật; cân bằng giữa độ sắc nét của vector và ngữ cảnh; top-5 chunk ≈ 4000 ký tự vừa với prompt |
| Vì sao chunk theo Điều? | Mỗi Điều là một đơn vị nghĩa trọn vẹn; cắt theo ký tự dễ chặt đôi một Khoản; metadata `article` phục vụ citation |
| Vì sao gắn tên văn bản vào mỗi chunk? | Số hiệu chỉ có ở trang đầu; không gắn thì BM25 không khớp query theo số hiệu (1/5 lên 5/5 chunk) |
| Index lại có bị trùng không? | Không: ID ổn định + upsert, và chunk thừa của cùng văn bản bị xoá |
| BM25 có điểm yếu gì với tiếng Việt? | Chưa tách từ ghép ("hộ kinh doanh" thành 3 token rời); cải thiện bằng `pyvi` |
| Vì sao sửa IDF của BM25Okapi? | IDF gốc bằng 0 hoặc âm khi từ phổ biến; corpus nhỏ thì mọi score bằng 0 |
| k = 60 trong RRF là gì? | Hằng số làm mượt: k lớn thì các hạng gần nhau hơn; 60 là giá trị chuẩn từ bài báo gốc |
| HNSW có chính xác tuyệt đối không? | Không, đây là tìm gần đúng (ANN); đổi chút độ chính xác lấy tốc độ, với corpus nhỏ thì gần như chính xác |
| Vì sao chọn OpenAI embedding? | Nhẹ máy, nhanh, rẻ, tiếng Việt tốt, dùng chung key với LLM. Trade-off: tốn phí mỗi lần index/eval và cần mạng |
