# Tài liệu kỹ thuật: Live Integration Test Runner (`test_run.py`)

## 1. Tổng quan
File `test_run.py` là script tích hợp phục vụ việc chạy thử nghiệm thực tế (integration testing) trên các hồ sơ tài liệu PDF thật đang lưu trữ trong thư mục làm việc của dự án. 

Không giống như `main.py` vốn tự tạo dữ liệu giả lập dạng text thô, script này thực hiện nạp trực tiếp các file PDF thực tế (trong đó có CV viết bằng tiếng Việt và chứa bố cục phức tạp) để kiểm tra hoạt động của module **Parsing & OCR Routing (Layer 2)**, độ chính xác của **Structured Extraction (Layer 3)** và hiệu quả của các **Hard-match Rules (Layer 5)** cùng **LLM Evaluation (Layer 6)**.

---

## 2. Thiết lập kỹ thuật
- **Encoding Console:** Cấu hình ép kiểu encoding của `sys.stdout` và `sys.stderr` về định dạng `utf-8` nếu môi trường hỗ trợ. Việc này cực kỳ quan trọng khi chạy thử nghiệm trên máy chủ Windows hoặc các terminal có font tiếng Việt để tránh gặp lỗi crash hoặc lỗi font chữ (hỏi chấm, ô vuông) khi in các trường văn bản tiếng Việt từ CV hoặc lý do đánh giá (`reasoning`) ra màn hình.
- **Cấu hình log:** Thiết lập logging ghi nhận thông tin ra stdout để giám sát từng bước thực thi trong pipeline.

---

## 3. Các tệp dữ liệu kiểm thử thực tế
Script liên kết với ba tệp tin PDF thực tế trong workspace:
1. `AI ENGINEER JD.pdf` (Tệp mô tả yêu cầu công việc kỹ sư trí tuệ nhân tạo).
2. `HoangThaiAnh_AIEngineer.pdf` (CV ứng viên Hoàng Thái Anh - tiếng Anh/vị trí AI).
3. `LeThanhNhanCVTiengViet.pdf` (CV ứng viên Lê Thanh Nhân - tiếng Việt).

---

## 4. Kịch bản thực thi tích hợp

### Bước 1: Kiểm tra tính sẵn sàng của dữ liệu
Kiểm tra sự tồn tại của file JD PDF. Nếu thiếu, chương trình dừng và thông báo lỗi. Nếu có, duyệt qua danh sách các CV PDF, lọc ra các tệp tin hiện hữu trên đĩa để chạy thử nghiệm và gán UUID tương ứng làm mã định danh ứng viên.

### Bước 2: Nạp CV vào Database (Ingestion Phase)
Khởi chạy lớp `CVMatcherPipeline` và thực hiện vòng lặp gọi hàm `pipeline.ingest_cv` cho các file CV PDF. Quá trình này sẽ trực tiếp kiểm thử:
- Khả năng đọc text layer của `pdfplumber` / `PyMuPDF`.
- Khả năng kích hoạt OCR tự động (nếu file là PDF scan).
- Khả năng gọi OpenAI / OpenRouter để chuyển đổi văn bản CV sang JSON Schema và lưu vào Vector DB.

### Bước 3: So khớp và tính điểm với Tin tuyển dụng thực tế
Sử dụng bộ trọng số chấm điểm chuyên môn chuẩn (`skills=45%`, `experience=35%`, `education=10%`, `culture=10%`).
Gọi hàm `pipeline.rank_candidates` truyền vào đường dẫn tệp tin `AI ENGINEER JD.pdf`. Phương thức này sẽ:
- Parse file JD PDF sang dạng văn bản.
- Trích xuất cấu trúc JD thành Schema bằng LLM.
- Chạy thuật toán tìm kiếm lai và tái xếp hạng trên cơ sở dữ liệu.
- Chạy đánh giá định lượng và định tính của LLM Scorer.

### Bước 4: Xuất báo cáo đánh giá thực tế
In báo cáo hoàn chỉnh ra màn hình bao gồm:
- Tên và ID ứng viên.
- Điểm đánh giá phù hợp tổng thể và biểu đồ điểm số thành phần.
- Kết quả kiểm duyệt các điều kiện cứng bao gồm: số năm kinh nghiệm thực tế (chỉ tính kinh nghiệm doanh nghiệp, loại bỏ tự học/dự án cá nhân), kỹ năng chuyên môn bắt buộc, học vị, chứng chỉ tiếng Anh (TOEIC/IELTS), trạng thái đã đi làm doanh nghiệp và cờ kết quả kiểm duyệt tổng quát.
- Các danh sách điểm mạnh, kỹ năng thiếu và lập luận đánh giá định tính chi tiết bằng tiếng Việt.
- Script này không dọn dẹp các tệp PDF vì đây là các tài liệu dữ liệu gốc của dự án.
