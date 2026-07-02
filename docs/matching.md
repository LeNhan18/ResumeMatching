# Tài liệu kỹ thuật: Multi-Dimensional Matching (`RAG/matching.py`)

## 1. Tổng quan
File `RAG/matching.py` đảm nhận vai trò **Layer 5 — Multi-Dimensional Matching** trong kiến trúc hệ thống. Đây là tầng trung gian chịu trách nhiệm thực hiện song song hai phương thức khớp hồ sơ:
1. **Hard-matching (Khớp cứng):** Thực hiện tính toán và kiểm duyệt các điều kiện tiên quyết (như số năm kinh nghiệm, kỹ năng cốt nôị, trình độ ngoại ngữ, phân loại kinh nghiệm doanh nghiệp) hoàn toàn bằng thuật toán Python thuần (deterministic logic).
2. **Soft-matching (Khớp mềm):** Kết hợp kết quả tìm kiếm ngữ nghĩa và tìm kiếm từ khóa thông qua giải thuật Reciprocal Rank Fusion (RRF), sau đó thực hiện tái xếp hạng (re-ranking) bằng mô hình Cross-Encoder học sâu, GraphScorer, hoặc bộ thuật toán Heuristic nâng cao.

---

## 2. Các hàm tiện ích ngày tháng

### `parse_date_string(date_str: Optional[str]) -> datetime`
- **Nhiệm vụ:** Chuẩn hóa nhiều định dạng ngày tháng xuất hiện trong CV thành đối tượng `datetime`.
- **Logic:**
  - Nếu rỗng hoặc chứa các từ chỉ công việc hiện tại (e.g. *present, current, đang làm, hiện tại, tới nay*), trả về thời gian hiện tại (`datetime.now()`).
  - Chuẩn hóa các dấu phân tách `/`, `\`, `.`, `-` thành dấu `-`.
  - Thử parse theo các định dạng phổ biến: `YYYY-MM`, `MM-YYYY`, `YYYY` (mặc định lấy ngày 1 tháng 1 của năm đó), `DD-MM-YYYY`.
  - Nếu hoàn toàn thất bại, ghi log debug và trả về thời gian hiện tại.

### `calculate_duration_months(start_str: str, end_str: Optional[str]) -> float`
- **Nhiệm vụ:** Tính khoảng thời gian làm việc quy đổi ra số tháng.
- **Logic:** Lấy ngày kết thúc trừ ngày bắt đầu ra số ngày thực tế, chia cho số ngày trung bình của một tháng (`30.4375`) để có kết quả chính xác, trả về tối thiểu `0.0`.

---

## 3. Module Khớp Cứng (`hard_match`)
*Hàm `hard_match(cv: CVSchema, jd: JDSchema) -> Dict[str, Any]` thực thi logic nghiệp vụ cố định, không phụ thuộc vào LLM để đảm bảo tính minh bạch và có thể kiểm toán.*

- **Quy trình tính toán:**
  1. **Tính tổng thời gian kinh nghiệm liên quan:**
     - Duyệt qua từng công việc trong danh sách `cv.experience`.
     - Loại bỏ các công việc là dự án cá nhân, đồ án môn học hoặc việc tự do (Freelance/Personal Project/Academic Project) dựa vào thuộc tính `experience_type` hoặc các từ khóa đặc trưng (như *freelance, cá nhân, bài tập, sinh viên, tốt nghiệp*).
     - Kiểm tra tính liên quan của công việc đó với JD:
       - Có chứa kỹ năng yêu cầu/ưu tiên của JD trong danh sách công nghệ đã dùng (`skills_used`).
       - Tên vị trí hoặc mô tả công việc có chứa từ khóa về mảng nghiệp vụ cần tuyển (`jd.domain`).
       - Ngành nghề công ty trùng khớp với ngành tuyển dụng (`jd.industry`).
     - Nếu thỏa mãn, tính số tháng công tác và cộng dồn. Kết quả cuối cùng được làm tròn sang số năm. Trạng thái `exp_passed` là `True` nếu số năm liên quan lớn hơn hoặc bằng yêu cầu tối thiểu của JD.
  2. **Kiểm tra độ phủ kỹ năng bắt buộc (`skills_passed`):**
     - Gom toàn bộ kỹ năng chung của ứng viên và kỹ năng từ các công việc cụ thể.
     - So khớp với tập kỹ năng yêu cầu bắt buộc của JD (`jd.required_skills`).
     - **Ràng buộc:** Ứng viên phải đáp ứng **tối thiểu 50%** lượng kỹ năng bắt buộc để vượt qua vòng lọc kỹ năng cứng.
  3. **Kiểm tra trình độ học vấn (`education_passed`):**
     - Đọc yêu cầu học vấn của JD. Lọc ra bằng cấp cao nhất trong CV.
     - So sánh cấp bậc (Master/Thạc sĩ, PhD/Tiến sĩ, Bachelor/Cử nhân/Kỹ sư) để đánh giá đạt/không đạt.
  4. **Kiểm tra ngoại ngữ (`has_english`):**
     - Duyệt các chứng chỉ (`certs`) và ngoại ngữ (`languages`) để tìm kiếm sự hiện diện của các chứng chỉ tiếng Anh chuẩn hóa: `ielts, toeic, toefl, pte, cefr, b1, b2, c1, c2`. Nếu không có, `has_english = False`.
  5. **Tính toán số năm kinh nghiệm thực tế (Corporate/Internship):**
     - Tính tổng số năm làm việc tại các doanh nghiệp (loại trừ freelance/đồ án học tập).
     - Thiết lập cờ `has_practical_exp` (nếu có từ 1 năm thực tế trở lên) và cờ `has_worked` (nếu đã từng đi làm hoặc thực tập tại tối thiểu 1 công ty). **Nếu chưa từng đi làm ở doanh nghiệp nào, ứng viên sẽ bị loại cứng (`overall_hard_match_passed = False`).**

---

## 4. Module Khớp Mềm & Rerank

### 4.1. Reciprocal Rank Fusion (`reciprocal_rank_fusion`)
- **Nhiệm vụ:** Kết hợp (fuse) thứ hạng từ hai danh sách kết quả tìm kiếm độc lập (Dense Search và Sparse Search).
- **Công thức tính điểm RRF:**
  $$RRF\_Score(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
  Trong đó $M$ là tập hợp các phương thức tìm kiếm, $r_m(d)$ là thứ tự xếp hạng của tài liệu $d$ trong phương thức $m$, và hằng số $k = 60$. Giải thuật này giúp tối ưu vị trí của những hồ sơ vừa khớp tốt về mặt ngữ nghĩa vừa chứa chính xác các từ khóa công nghệ cần tìm.

### 4.2. Bộ tái xếp hạng (`Reranker`)
Lớp `Reranker` thực hiện tối ưu hóa thứ tự hiển thị của các ứng viên hàng đầu.

#### Phương thức `rerank(self, query: str, candidates: List[Dict[str, Any]], jd: JDSchema = None, limit: int = 5)`
- **Logic hoạt động:**
  - Nếu cấu hình biến môi trường `USE_LOCAL_RERANKER` là `true` và thư viện `sentence-transformers` được cài đặt: Tải mô hình học sâu **Cross-Encoder** (`cross-encoder/ms-marco-MiniLM-L-6-v2`). Nó sẽ chấm điểm tương tác ngữ nghĩa trực tiếp giữa nội dung JD (truy vấn) và toàn bộ text của CV. Điểm số được đưa qua hàm sigmoid để chuẩn hóa về khoảng `(0, 1)` và sắp xếp lại.
  - Nếu không, tự động chuyển sang chế độ Heuristic nâng cao (`_heuristic_rerank`).

#### Phương thức `_heuristic_rerank(self, query: str, candidates: List[Dict[str, Any]], jd: JDSchema = None, limit: int = 5)`
- **Thuật toán tính điểm ưu tiên nội bộ:**
  - **Jaccard Similarity:** Tính tỷ lệ trùng từ khóa (token overlap) giữa text JD và text CV.
  - **Graph Semantic Score & Insights (Layer 5.5):** Gọi qua hàm `get_graph_score_and_insights` của `GraphScorer` để tính điểm ngữ nghĩa đồ thị cho ứng viên dựa trên `cv_id` (Anchor Node). Hàm này áp dụng nguyên tắc DRY, trả về đồng thời điểm số (`total_score`) và mảng các câu giải thích (`insights`) trong duy nhất 1 lần gọi Cypher:
    - So khớp kỹ năng tương đương qua cạnh `ALTERNATIVE_TO` (Max 0.3).
    - So khớp chức danh tương đương qua cạnh `EQUIVALENT_TO` (Max 0.3).
    - So khớp ngành nghề công ty cũ qua cạnh `BELONGS_TO` (Max 0.2).
    - So khớp ngành học liên quan qua cạnh `RELATED_MAJOR` (Max 0.2).
    *(Tổng Graph Score tối đa = 1.0. Mảng `graph_insights` thu được sẽ gắn vào kết quả để truyền cho Layer 6).*
  - **Sparse Score Normalization:** Chuẩn hóa điểm BM25 của Qdrant về khoảng `[0.0, 1.0]` bằng cách chia cho `max_sparse`.
  - **Heuristic Boosts:** Cộng `+0.15` cho English Cert, và tối đa `+0.25` cho Corporate Experience.
  - **Công thức tổng hợp điểm Rerank (Tỷ trọng vàng):**
    $$Rerank\_Score = (Dense \times 0.3) + (Sparse_{norm} \times 0.2) + (Jaccard \times 0.1) + (Graph\_Score \times 0.4) + Heuristic\_Boosts$$
  - Sắp xếp và trả về danh sách ứng viên phù hợp nhất theo giới hạn `limit`.
