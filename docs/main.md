# Tài liệu kỹ thuật: Command-line Demo Simulation (`main.py`)

## 1. Tổng quan
File `main.py` là một ứng dụng giao diện dòng lệnh (CLI) độc lập được thiết kế nhằm mục đích **mô phỏng, kiểm thử và demo nhanh** toàn bộ hoạt động của hệ thống AI CV Matcher RAG Pipeline. 

Khi khởi chạy, file tự động tạo lập dữ liệu giả lập (gồm các file CV định dạng Word, file CV text và JD), chạy qua toàn bộ pipeline 6 tầng và in chi tiết báo cáo đánh giá ra màn hình console, sau đó tự động thu dọn toàn bộ các file rác phát sinh.

---

## 2. Các hàm hỗ trợ khởi tạo dữ liệu mẫu

### `create_sample_docx_cv(file_path: str)`
- **Nhiệm vụ:** Tạo file Word (`.docx`) mô phỏng một CV của ứng viên tên "NGUYEN PHAN TIEN".
- **Nội dung giả lập:**
  - Vị trí: Backend Engineer (IT / Fintech) có 4 năm kinh nghiệm.
  - Học vấn: Đại học Bách Khoa Hà Nội (HUST).
  - Chứng chỉ: AWS Certified Developer, Docker Certified Associate.
  - Kinh nghiệm: Làm việc tại "Fintech Solutions Corp" (Senior, 2022-nay) và "Tech Startup Lab" (Junior, 2020-2022).
  - Kỹ năng sử dụng: Python, FastAPI, Docker, PostgreSQL, Redis, Flask.
- **Logic:** Sử dụng thư viện `python-docx` để tạo định dạng Heading, Paragraph có kiểu chữ in đậm. Nếu hệ thống chưa cài đặt `python-docx`, hàm tự động ghi nhận cảnh báo và chuyển hướng sang sinh file văn bản thuần `.txt` thay thế làm giải pháp dự phòng.

### `create_sample_text_cv(file_path: str)`
- **Nhiệm vụ:** Tạo file văn bản thuần (`.txt`) mô phỏng CV của ứng viên tên "TRAN HONG NHUNG".
- **Nội dung giả lập:**
  - Vị trí: Frontend Developer chuyên ReactJS có 3 năm kinh nghiệm.
  - Học vấn: Đại học Khoa học Tự nhiên TP.HCM (HCMUS).
  - Kinh nghiệm: Làm việc tại "E-Commerce Hub" và "Web agency".
  - Kỹ năng sử dụng: ReactJS, JavaScript, HTML5, CSS3, TailwindCSS, Git.

### `create_sample_jd(file_path: str)`
- **Nhiệm vụ:** Tạo file mô tả công việc (`sample_jd.txt`) cho vị trí **Senior Backend Engineer** tại "Cyber Finance Inc".
- **Nội dung giả lập:**
  - Lĩnh vực: Backend (IT / Fintech).
  - Yêu cầu kinh nghiệm: Tối thiểu **3.0 năm**.
  - Kỹ năng bắt buộc (Mandatory): Python, Docker, PostgreSQL.
  - Kỹ năng ưu tiên (Nice-to-have): Kubernetes, AWS/GCP, FastAPI, Go.

---

## 3. Luồng hoạt động chính (`main`)

### Bước 1: Khởi tạo dữ liệu thử nghiệm
Ghi các file giả lập ra đĩa cứng tại thư mục gốc: `sample_cv_1.docx`, `sample_cv_2.txt`, và `sample_jd.txt`.

### Bước 2: Kích hoạt Pipeline
Khởi tạo đối tượng `CVMatcherPipeline`. Tiến hành nạp (ingest) 2 file CV của ứng viên Nguyễn Phan Tiến (mã định danh `cand_tien`) và Trần Hồng Nhung (mã định danh `cand_nhung`). Hệ thống sẽ chạy qua các bước OCR/Parse và Structured Extraction để đưa thông tin lên database.

### Bước 3: Thiết lập Rubric chấm điểm
Định nghĩa hệ trọng số phân bổ tiêu chí chấm điểm chuyên môn cho vị trí kỹ thuật:
- Khớp kỹ năng chuyên môn (`skills`): **45%**.
- Số năm & chất lượng kinh nghiệm (`experience`): **35%**.
- Trình độ học vấn (`education`): **10%**.
- Độ hòa hợp văn hóa (`culture_fit`): **10%**.

### Bước 4: So khớp và tính điểm
Gọi hàm `pipeline.rank_candidates` truyền vào đường dẫn file JD, hệ trọng số và giới hạn lấy tối đa `5` ứng viên.

### Bước 5: In báo cáo kết quả chi tiết
Duyệt qua danh sách ứng viên đã được xếp hạng để in ra màn hình console:
1. **Thông tin chung:** Họ tên ứng viên, điểm số khớp tổng hợp (`score` %).
2. **Điểm thành phần:** Chi tiết điểm của 4 cột tiêu chí (Kỹ năng, Kinh nghiệm, Học vấn, Văn hóa).
3. **Kết quả kiểm duyệt Hard-match:**
   - Số năm kinh nghiệm liên quan tính toán được so với yêu cầu tuyển dụng.
   - Danh sách kỹ năng bắt buộc trùng khớp.
   - Đạt/không đạt yêu cầu học vị tối thiểu.
   - Có chứng chỉ tiếng Anh quốc tế hay không.
   - Trạng thái kiểm duyệt tổng thể (Overall status).
4. **Nhận xét định tính:** Danh sách điểm mạnh nổi bật, danh sách công nghệ còn thiếu, và văn bản lập luận phân tích chi tiết.

### Bước 6: Dọn dẹp tài nguyên
Duyệt qua danh sách các file tạm đã tạo ở Bước 1 và tiến hành xóa chúng khỏi hệ thống đĩa để khôi phục trạng thái sạch cho workspace.
