# Tài liệu kỹ thuật: FastAPI Web Server (`app.py`)

## 1. Tổng quan
File `app.py` là cổng kết nối HTTP chính của ứng dụng, triển khai một RESTful API server sử dụng framework **FastAPI**. Server này cung cấp các endpoint giao tiếp trực tiếp với giao diện người dùng (Frontend), quản lý vòng đời tệp tin tải lên (upload/delete CV, JD) và cung cấp các hàm hỗ trợ demo dữ liệu mẫu.

---

## 2. Thiết lập cấu hình hệ thống
- **CORS Middleware:** Cấu hình mở rộng (`allow_origins=["*"]`) cho phép mọi nguồn domain Frontend kết nối đến để thuận tiện cho quá trình phát triển (development).
- **Thư mục lưu trữ vật lý:**
  - `/uploads`: Lưu trữ lâu dài các file CV tải lên để người dùng có thể tải về hoặc xem lại. Các file được đặt tên kèm tiền tố UUID để tránh trùng lặp.
  - `/temp`: Thư mục lưu trữ tạm thời các file JD tải lên để phục vụ phân tích trích xuất, tự động dọn dẹp (xóa file) ngay sau khi quá trình so khớp hoàn tất.
- **Phục vụ Frontend (Static Files):** Kiểm tra sự tồn tại của thư mục build `frontend/dist`. Nếu tồn tại, server sẽ tự động mount thư mục này lên root path `/` sử dụng `StaticFiles` để chạy ứng dụng Single-Page (SPA) trực tiếp trên port của API.

---

## 3. Danh sách các API Endpoints

### 3.1. Health Check
- **Endpoint:** `GET /api/health`
- **Nhiệm vụ:** Kiểm tra tình trạng hoạt động của hệ thống.
- **Đầu ra:** Trạng thái hoạt động của server (`healthy`), tính sẵn sàng của pipeline AI, và trạng thái kết nối tới cơ sở dữ liệu Vector DB (Qdrant).

### 3.2. Lấy danh sách ứng viên
- **Endpoint:** `GET /api/candidates`
- **Nhiệm vụ:** Liệt kê toàn bộ thông tin ứng viên đã index.
- **Logic:** Gọi hàm `pipeline.vector_db.list_all_cvs()` trả về danh sách các payload CV (không bao gồm vector).

### 3.3. Tải lên CV ứng viên
- **Endpoint:** `POST /api/upload_cv`
- **Tham số đầu vào:** Tệp tin CV dạng Multipart Form (`file: UploadFile`).
- **Logic hoạt động:**
  1. Tạo mã định danh ngẫu nhiên `cv_id` dạng UUID.
  2. Tạo thư mục `/uploads` nếu chưa tồn tại. Lưu tệp tin vật lý dưới tên `[cv_id]_[tên_file_gốc]`.
  3. Gọi `pipeline.ingest_cv(saved_path, cv_id)` để kích hoạt quy trình Layer 2 & 3 (Parse và Structuring) rồi lưu vào CSDL.
  4. Nếu gặp bất kỳ lỗi nào trong quá trình xử lý, hệ thống tự động xóa file vật lý vừa lưu để tránh rác ổ đĩa và trả về mã lỗi HTTP 500.

### 3.4. Xóa ứng viên khỏi hệ thống
- **Endpoint:** `DELETE /api/candidates/{id}`
- **Tham số đầu vào:** Mã định danh ứng viên `id` truyền qua URL.
- **Logic hoạt động:**
  1. Lấy thông tin payload của ứng viên từ DB để truy tìm đường dẫn file vật lý đã lưu trên đĩa cứng (`file_path`).
  2. Thực hiện lệnh xóa ứng viên khỏi DB.
  3. Tiến hành xóa file vật lý trên đĩa cứng tương ứng. Trả về mã lỗi nếu ứng viên không tồn tại trong DB.

### 3.5. Thực hiện so khớp & xếp hạng
- **Endpoint:** `POST /api/match`
- **Tham số đầu vào:** Nhận dữ liệu dưới dạng Form Data:
  - `jd_text` (Optional): Đoạn văn bản mô tả công việc.
  - `jd_file` (Optional): Tệp tin JD tải lên.
  - `weights` (str): Chuỗi JSON chứa cấu hình trọng số chấm điểm.
- **Logic hoạt động:**
  1. Parse chuỗi `weights` thành đối tượng cấu trúc `ScoringWeights`.
  2. Xác định nguồn JD:
     - Nếu HR tải file JD lên: Lưu tạm vào thư mục `/temp` với tên sinh ngẫu nhiên dạng UUID. Đường dẫn file tạm này sẽ được coi là nguồn JD (`jd_source`).
     - Nếu HR paste text: Chuỗi text trực tiếp là nguồn JD (`jd_source`).
  3. Gọi hàm xếp hạng `pipeline.rank_candidates(jd_source, weights, limit=10)`.
  4. Giải phóng tài nguyên: Thực hiện xóa tệp tin tạm của JD trong thư mục `/temp` để bảo vệ tài nguyên hệ thống.

### 3.6. Tự động tải dữ liệu demo (Helper Endpoints)
- **Endpoint:** `POST /api/load_samples`
- **Nhiệm vụ:** Sao chép các tệp tin CV mẫu có sẵn trong thư mục gốc (`HoangThaiAnh_AIEngineer.pdf` và `LeThanhNhanCVTiengViet.pdf`) vào thư mục lưu trữ lâu dài `/uploads` và tự động kích hoạt tiến trình nạp (ingest) để tiện chạy thử nghiệm nhanh.
- **Endpoint:** `GET /api/load_sample_jd`
- **Nhiệm vụ:** Tự động parse tệp tin `AI ENGINEER JD.pdf` có sẵn trong workspace và trả về văn bản đã trích xuất, hỗ trợ điền nhanh dữ liệu vào khung soạn thảo JD ở Frontend.
