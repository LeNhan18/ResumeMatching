# Tài liệu kỹ thuật: CV Matcher Pipeline (`RAG/pipeline.py`)

## 1. Tổng quan
File `RAG/pipeline.py` là trung tâm điều phối của toàn bộ hệ thống AI Matcher. Lớp `CVMatcherPipeline` đóng vai trò là một **Facad Pattern**, kết nối và điều phối các module độc lập như: Parser (Layer 2), Extractor & DB (Layer 3 & 4), Matching (Layer 5) và Scorer (Layer 6) thành một luồng xử lý đồng nhất (end-to-end pipeline).

---

## 2. Khởi tạo `__init__`
Khi khởi tạo đối tượng `CVMatcherPipeline`, nó tự động tạo các thực thể đại diện cho các tầng xử lý:
- `llm_client`: Khách hàng giao tiếp LLM.
- `embedding_service`: Dịch vụ tạo vector ngữ nghĩa và từ khóa thưa thớt.
- `vector_db`: Client kết nối và quản lý dữ liệu trên Qdrant/RAM.
- `reranker`: Bộ tái xếp hạng kết quả tìm kiếm.
- `scorer`: Bộ chấm điểm định tính dựa trên VLM/LLM.

---

## 3. Các phương thức điều phối chính

### 3.1. Phương thức `ingest_cv(self, file_path: str, cv_id: str) -> CVSchema`
*Quy trình nạp và phân tích hồ sơ ứng viên vào hệ thống.*
- **Tham số:** `file_path` (đường dẫn file CV), `cv_id` (mã định danh duy nhất của ứng viên).
- **Đầu ra:** Thực thể `CVSchema` chứa dữ liệu cấu trúc đã lưu vào cơ sở dữ liệu.
- **Quy trình hoạt động:**
  1. **Đọc văn bản thô:** Gọi `parse_document(file_path)` từ module PARSING để trích xuất text. Nếu text trống, ném lỗi `ValueError`.
  2. **Trích xuất thông tin bằng LLM (Structuring):** 
     - Thiết lập hệ thống prompt chỉ định rõ vai trò HR trích xuất dữ liệu của LLM.
     - Áp đặt quy tắc phân loại chặt chẽ đối với lịch sử làm việc của ứng viên (`experience_type`):
       - Phân biệt rõ các mục nằm trong nhóm "PROJECTS" (Dự án) và "WORK EXPERIENCE" (Kinh nghiệm làm việc) để gán nhãn chính xác: `Corporate` (Làm doanh nghiệp), `Internship` (Thực tập), `Freelance` (Làm tự do), `Personal Project` (Dự án cá nhân), hoặc `Academic Project` (Đồ án học tập).
     - Gửi prompt và raw text của CV yêu cầu LLM trích xuất dữ liệu ép kiểu về cấu trúc `CVSchema`.
  3. **Lưu trữ vào CSDL Vector:**
     - Gọi `vector_db.upsert_cv(cv_id, cv_text, cv_payload)`. 
     - Lưu kèm đường dẫn file vật lý (`file_path`) trong payload để hỗ trợ việc quản lý/xóa file sau này.
  4. **Lưu trữ vào CSDL Đồ thị (Graph DB):**
     - Kêu gọi `graph_extractor.extract_graph_from_cv(..., document_id=cv_id)` để trích xuất các Node và Edge từ CV.
     - Đảm bảo tính nhất quán dữ liệu bằng cách sử dụng chung mã `cv_id` (UUID) cho `Candidate` node.

---

### 3.2. Phương thức `ingest_jd(self, file_path_or_text: str) -> JDSchema`
*Quy trình nạp và phân tích yêu cầu tuyển dụng.*
- **Tham số:** `file_path_or_text` (Có thể là đường dẫn file PDF/DOCX JD hoặc trực tiếp là đoạn text mô tả công việc).
- **Đầu ra:** Thực thể `JDSchema` chứa các yêu cầu tuyển dụng cốt lõi.
- **Quy trình hoạt động:**
  1. Tự động kiểm tra xem tham số truyền vào là một đường dẫn file có thật trên đĩa hay là text thuần. Nếu là file, gọi `parse_document` để chuyển đổi sang văn bản.
  2. Gửi văn bản mô tả công việc tới LLM để trích xuất các thông tin cần tuyển dụng: Vị trí, các kỹ năng bắt buộc, kỹ năng ưu tiên, số năm kinh nghiệm tối thiểu yêu cầu, trình độ học vấn... ép kiểu về cấu trúc `JDSchema`.

---

### 3.3. Phương thức `match_cv_to_jd(self, cv_id: str, jd: JDSchema, weights: Optional[ScoringWeights] = None) -> ScoringResult`
*So khớp trực tiếp một ứng viên cụ thể trong database với một JD đã định nghĩa.*
- **Logic hoạt động:**
  1. Lấy dữ liệu payload của ứng viên từ Vector DB bằng `cv_id`. Trả về lỗi nếu ứng viên không tồn tại.
  2. Khôi phục thực thể `CVSchema` từ payload.
  3. Chạy thuật toán **Hard-match** để kiểm duyệt các tiêu chuẩn cứng (Layer 5).
  4. **Tính toán Soft-match cục bộ:**
     - Gọi `expander.build_enriched_query(jd)` để lấy chuỗi Super-Query (nếu cần thiết cho việc đồng bộ format văn bản).
     - Tạo dense vector tương ứng cho văn bản của CV ứng viên và JD.
     - Tính Cosine similarity của hai vector và chuẩn hóa về khoảng `[0.0, 1.0]`.
  5. **Đánh giá LLM Scorer (Bypass Graph Insights):**
     - Ở luồng Single Match này, hệ thống cố tình **bypass (bỏ qua)** luồng trích xuất Graph Insights từ CSDL Đồ thị nhằm giữ nguyên bản chất là thuật toán Vector Similarity thuần túy 1-1.
     - Truyền mảng rỗng `graph_insights=[]` xuống `scorer` để tiến hành đánh giá định lượng và chất lượng dựa trên Vector và Hard Match.

---

### 3.4. Phương thức `rank_candidates(self, jd_text_or_file: str, weights: Optional[ScoringWeights] = None, limit: int = 5) -> List[Dict[str, Any]]`
*Tìm kiếm và xếp hạng toàn bộ ứng viên phù hợp nhất trong hệ thống cho một tin tuyển dụng.*
- **Quy trình hoạt động:**
  1. Gọi `ingest_jd` để lấy thông tin cấu trúc của tin tuyển dụng.
  2. Sử dụng `QueryExpander` để kích hoạt Just-in-Time Wiring (kết nối Graph tức thì) và xây dựng chuỗi truy vấn mở rộng (Expanded Query).
  3. Thực hiện **Tìm kiếm lai (Hybrid Search)** trên Vector DB thông qua `vector_db.search_cv` để lấy ra danh sách các ứng viên khớp từ khóa (BM25) và khớp ý nghĩa (Dense Vector). Tìm kiếm số lượng lớn hơn (`limit * 3`) để có đủ mẫu tái xếp hạng.
  4. Thực hiện **Tái xếp hạng (Re-ranking)** danh sách trên thông qua bộ `reranker.rerank(..., jd=jd)`. Bộ Reranker sẽ kết hợp Dense, Sparse, Jaccard và đặc biệt là **Graph Score** để lọc ra top ứng viên tiềm năng nhất (`limit`).
  5. Duyệt qua danh sách top ứng viên này:
     - Khôi phục thực thể `CVSchema`.
     - Chạy kiểm duyệt Hard-match.
     - Trích xuất lời giải thích đồ thị `graph_insights` (được sinh ra từ Reranker).
     - Chạy đánh giá định lượng và chất lượng bằng `LLMScorer`, bơm mảng `graph_insights` vào Prompt để cung cấp năng lực giải thích (Explainable AI) cho LLM bảo vệ điểm số ứng viên.
  6. Sắp xếp lại danh sách kết quả cuối cùng theo điểm số đánh giá thực tế (`match_score`) từ cao xuống thấp và trả về client.
