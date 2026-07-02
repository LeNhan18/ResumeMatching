# Tài liệu kỹ thuật: Vector Database & Embedding Service (`RAG/vector_db.py`)

## 1. Tổng quan
File `RAG/vector_db.py` cấu thành **Layer 4 — Embedding & Indexing** trong kiến trúc hệ thống. Module này đảm nhận vai trò chuyển hóa dữ liệu văn bản thô từ CV và JD thành các biểu diễn vector dày đặc (dense embeddings) và vector thưa thớt (sparse representations), đồng thời lưu trữ và truy vấn chúng trên cơ sở dữ liệu vector **Qdrant** (hoặc cơ sở dữ liệu giả lập lưu trong bộ nhớ RAM làm dự phòng).

---

## 2. Dịch vụ tạo Vector (`EmbeddingService`)
Lớp này đóng gói toàn bộ logic tạo vector biểu diễn ngữ nghĩa cho văn bản.

### 2.1. Hàm khởi tạo `__init__`
- Kiểm tra biến môi trường `USE_LOCAL_EMBEDDING` (nếu là `true`, tải thư viện `sentence-transformers` và nạp mô hình cục bộ **`BAAI/bge-m3`** với số chiều vector là `1024`).
- Nếu không sử dụng mô hình local, hệ thống mặc định cấu hình sử dụng mô hình qua API của OpenAI là `text-embedding-3-small` (số chiều `1536`).

### 2.2. Phương thức `get_dense_embedding(self, text: str) -> List[float]`
- **Đầu vào:** Chuỗi văn bản cần vector hóa.
- **Đầu ra:** Mảng số thực biểu diễn vector ngữ nghĩa.
- **Logic:**
  1. Thử sinh embedding cục bộ bằng BGE-M3 (nếu được kích hoạt).
  2. Nếu không, thử gọi API sinh embedding của OpenAI thông qua `llm_client`.
  3. Nếu cả hai cách đều không khả dụng (ví dụ: mất mạng, thiếu API key), gọi hàm dự phòng `_generate_mock_embedding` để tạo một vector giả lập đơn vị đảm bảo hệ thống không bị crash.

### 2.3. Phương thức `_generate_mock_embedding(self, text: str) -> List[float]`
- **Nhiệm vụ:** Tạo ra một vector giả lập cố định dựa trên băm (hash) các ký tự của văn bản, đảm bảo tính nhất quán (cùng một văn bản luôn sinh ra cùng một vector mock).
- **Logic:** Cắt nhỏ văn bản tương ứng với số chiều vector (`1536` hoặc `1024`), băm MD5 từng đoạn để lấy giá trị số thực từ `-5000` đến `5000`, sau đó chuẩn hóa mảng thu được về dạng vector đơn vị (độ dài vector = `1.0`) để phục vụ tính toán Cosine Similarity chuẩn xác.

### 2.4. Phương thức `get_sparse_representation(self, text: str) -> Dict[str, float]`
*Dành cho việc index từ khóa để hỗ trợ Sparse Search (tương tự BM25).*
- **Đầu vào:** Một đoạn văn bản.
- **Đầu ra:** Một dictionary map `{từ_khóa: trọng_số}`.
- **Logic:** Dùng regex tách các từ trong văn bản (bỏ qua ký tự đơn lẻ), tính tần suất xuất hiện (Term Frequency - TF) của từng từ, sau đó áp dụng công thức chuẩn hóa phi tuyến tính (sublinear scaling) để tính ra trọng số của từ khóa: `0.5 + 0.5 * (tf / max_tf)`.

---

## 3. Vector Database Giả Lập (`InMemoryVectorStore`)
*Lớp này đóng vai trò cơ sở dữ liệu vector dự phòng (fallback) chạy trực tiếp trong RAM nếu không có kết nối Qdrant.*
- **`upsert`**: Lưu trữ tài liệu (dense vector, sparse vector và thông tin payload) và tính toán lại chỉ số nghịch đảo tần suất xuất hiện trong tài liệu (IDF) cho toàn bộ từ vựng trong database.
- **`_recalculate_idf`**: Tính toán Inverse Document Frequency (IDF) cho từng từ trong từ điển theo công thức chuẩn hóa của BM25: `ln(1 + (N - n + 0.5) / (n + 0.5)) + 1.0`.
- **`search`**: Duyệt qua danh sách tài liệu trong bộ nhớ:
  - Áp dụng các điều kiện lọc cứng (metadata filtering).
  - Tính điểm tương đồng Cosine (tích vô hướng của dense vector truy vấn và dense vector tài liệu).
  - Tính điểm khớp từ khóa (Sparse Score) bằng cách nhân trọng số sparse query với sparse document và nhân thêm giá trị IDF của từ đó. Điểm sparse sau cùng được chuẩn hóa qua hàm sigmoid về khoảng `(0, 1)`.
  - Trả về danh sách kết quả xếp hạng.

---

## 4. Client Cơ Sở Dữ Liệu Vector (`VectorDBClient`)
Lớp giao tiếp chính để quản lý dữ liệu CV trong DB.

### 4.1. Hàm khởi tạo `__init__`
- Kết nối tới cluster Qdrant thông qua biến môi trường `QDRANT_URL` và `QDRANT_API_KEY`.
- Nếu thiếu cấu hình hoặc import thư viện `qdrant-client` bị lỗi, tự động hạ cấp xuống sử dụng `InMemoryVectorStore`.
- Nếu kết nối Qdrant thành công, gọi hàm khởi tạo collection.

### 4.2. Phương thức `_initialize_collection(self)`
- Khởi tạo collection trong Qdrant (mặc định tên là `cv_matcher`).
- Cấu hình đa vector (Multi-vector):
  - Vector `"dense"`: Sử dụng khoảng cách `COSINE` và kích thước động tương ứng với embedding model.
  - Vector `"sparse"`: Sử dụng cấu hình sparse vector index của Qdrant (bật tính năng ghi lên đĩa `on_disk=True` để tối ưu bộ nhớ).

### 4.3. Phương thức `upsert_cv(self, cv_id: str, text: str, payload: Dict[str, Any])`
- Nhận thông tin text của CV và dữ liệu cấu trúc Pydantic đã chuyển sang dict (`payload`).
- Tạo dense embedding và sparse representation cho văn bản CV.
- Vì Qdrant yêu cầu chỉ số sparse vector là các số nguyên, hệ thống chuyển đổi từ khóa dạng chuỗi (`token`) thành các số nguyên định danh bằng cách lấy băm MD5 của token chia lấy dư cho `2147483647`.
- Gọi API `real_client.upsert` để lưu trữ dữ liệu đa vector vào Qdrant. Nếu lỗi, chuyển sang lưu vào `local_store` dự phòng.

### 4.4. Phương thức `search_cv(self, query: str, limit: int = 10, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]`
- Nhận câu truy vấn tìm kiếm (JD hoặc các từ khóa yêu cầu từ JD).
- Tạo dense query vector và sparse query vector.
- Chuyển đổi metadata filter sang định dạng Filter của Qdrant (hỗ trợ `MatchValue` hoặc `MatchAny` đối với mảng giá trị).
- Thực hiện song song hai truy vấn tìm kiếm:
  1. Tìm kiếm ngữ nghĩa bằng dense vector: Gọi `query_points` trên không gian vector `"dense"`.
  2. Tìm kiếm từ khóa bằng sparse vector: Gọi `query_points` trên không gian vector `"sparse"`.
- Gom nhóm kết quả (chập kết quả của 2 luồng truy vấn theo `candidate_id`), gán điểm dense score và sparse score độc lập để chuyển tiếp sang module so khớp xếp hạng ở Layer 5.
- Trường hợp Qdrant lỗi, tự động chuyển đổi sang tìm kiếm trên `local_store` dự phòng.

### 4.5. Các phương thức bổ trợ
- `get_cv(self, cv_id: str)`: Lấy ra thông tin payload gốc của một ứng viên theo ID.
- `list_all_cvs(self)`: Duyệt cuộn (scroll) lấy toàn bộ danh sách các ứng viên đang được index trong DB (không tải kèm vector để tối ưu tốc độ mạng).
- `delete_cv(self, cv_id: str)`: Xóa một ứng viên khỏi index của Qdrant và/hoặc InMemory store, đồng thời tính toán lại tần suất từ vựng IDF.
