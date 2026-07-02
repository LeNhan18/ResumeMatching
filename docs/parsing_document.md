# Tài liệu kỹ thuật: Document Parsing & OCR Router (`PARSING/ParsingDocument.py`)

## 1. Tổng quan
File `PARSING/ParsingDocument.py` đảm nhận vai trò **Layer 2 — Parsing & OCR** trong kiến trúc hệ thống. Đây là một pipeline thông minh tự động phát hiện định dạng tệp tin đầu vào (PDF, DOCX, Ảnh scan, văn bản thuần) và định tuyến (routing) sang bộ công cụ đọc thích hợp nhất. 

Đặc biệt, module này có khả năng tự động phát hiện tài liệu dạng Scan (hình ảnh/PDF scan không có text layer) để kích hoạt cơ chế OCR cục bộ (Surya OCR) hoặc gọi VLM API đám mây (Qwen-VL) để đọc hiểu cấu trúc bố cục phức tạp.

---

## 2. Các thư viện sử dụng
- `pdfplumber`: Đọc file PDF native chính xác cao, hỗ trợ tùy chọn `layout=True` để giữ nguyên cấu trúc hiển thị trực quan (ví dụ các cột, block).
- `fitz` (`PyMuPDF`): Dùng làm fallback trích xuất text PDF native nhanh, đồng thời là thư viện render các trang của file PDF thành ảnh bitmap (`Pixmap`) phục vụ cho tiến trình OCR.
- `docx` (`python-docx`): Trích xuất văn bản từ file Word (`.docx`), đọc cả các đoạn văn bản (paragraphs) và dữ liệu dạng bảng biểu (tables).
- `PIL.Image`: Xử lý hình ảnh.
- `surya`: Thư viện OCR cục bộ thế hệ mới giúp nhận diện bounding box, cột và text dòng chữ rất tốt trên GPU/CPU.
- `LLM.client` & `base64`: Hỗ trợ mã hóa ảnh gửi lên Vision-Language Model để thực hiện OCR bằng trí tuệ nhân tạo.

---

## 3. Các hàm xử lý chi tiết

### Hàm `parse_pdf_native(file_path: str) -> str`
- **Nhiệm vụ:** Trích xuất text từ tệp PDF có chứa sẵn lớp ký tự (Native PDF).
- **Logic:**
  1. Thử sử dụng `pdfplumber`. Duyệt từng trang, gọi `page.extract_text(layout=True)`. Việc giữ nguyên layout là cực kỳ quan trọng đối với CV vì nó giúp giữ nguyên cấu trúc dòng và cột trực quan của ứng viên.
  2. Nếu không cài đặt `pdfplumber` hoặc gặp lỗi, hệ thống ghi log cảnh báo và fallback sang dùng `fitz` (PyMuPDF). `fitz` mở file PDF và lấy text qua phương thức `page.get_text("text")`.
  3. Trả về toàn bộ text được ghép lại, hoặc chuỗi rỗng nếu thất bại.

---

### Hàm `parse_docx(file_path: str) -> str`
- **Nhiệm vụ:** Đọc tệp Word định dạng `.docx`.
- **Logic:**
  1. Khởi tạo đối tượng `Document` từ `python-docx`.
  2. Lấy toàn bộ text từ danh sách paragraphs: `[p.text for p in doc.paragraphs]`.
  3. Duyệt qua các bảng biểu (`doc.tables`) trong file Word. Với mỗi dòng (`row`), nối text các ô lại bằng dấu phân cách ` | ` để không bị mất liên kết thông tin dòng-cột.
  4. Trả về text gộp từ cả paragraphs và tables.

---

### Hàm `pdf_to_images(pdf_path: str) -> list`
- **Nhiệm vụ:** Chuyển đổi toàn bộ các trang của file PDF thành danh sách các ảnh PIL để sẵn sàng OCR.
- **Logic:** Sử dụng `PyMuPDF` để mở tệp, duyệt qua từng trang, gọi `page.get_pixmap(dpi=150)` để render trang đó thành ảnh PNG với độ phân giải trung bình (150 DPI), sau đó chuyển đổi dữ liệu nhị phân thành đối tượng ảnh PIL.

---

### Hàm `parse_with_surya(images: list) -> str`
- **Nhiệm vụ:** Nhận diện ký tự quang học (OCR) cục bộ bằng thư viện Surya OCR.
- **Logic:**
  1. Import các hàm `run_ocr` và tải mô hình nhận diện dòng chữ (detection model) + mô hình nhận dạng ký tự (recognition model).
  2. Thiết lập ngôn ngữ nhận diện bao gồm tiếng Việt và tiếng Anh (`langs = ["vi", "en"]`).
  3. Gọi mô hình xử lý hàng loạt danh sách ảnh đầu vào.
  4. Duyệt kết quả dự đoán và nối các dòng chữ (`line.text`) lại với nhau theo thứ tự đọc tự nhiên của layout.

---

### Hàm `parse_with_vlm(images: list) -> str`
- **Nhiệm vụ:** Thực hiện OCR thông minh qua Vision-Language Model (mặc định là `qwen/qwen3-vl-32b-instruct` qua OpenRouter API).
- **Logic:**
  1. Khởi tạo `LLMClient`. Mã hóa ảnh PIL thành chuỗi Base64 định dạng JPEG.
  2. Tạo prompt yêu cầu VLM: *"Trích xuất và sao chép lại toàn bộ văn bản từ trang này. Giữ nguyên bố cục và cấu trúc trực quan (như cột, danh sách, khối kinh nghiệm)"*.
  3. Gửi payload ảnh Base64 và prompt qua API chat completion của OpenAI client tương thích OpenRouter.
  4. Nhận kết quả văn bản trả về cho từng trang và ghép lại bằng dấu ngắt trang `\n\n`.

---

### Hàm `parse_image_ocr(file_path: str) -> str`
- **Nhiệm vụ:** Điều hướng tiến trình OCR cho tệp ảnh đơn lẻ (`.png`, `.jpg`, `.jpeg`, `.webp`) hoặc tệp PDF dạng scan.
- **Logic:**
  1. Load ảnh trực tiếp qua PIL Image nếu là tệp ảnh, hoặc render PDF ra ảnh thông qua hàm `pdf_to_images`.
  2. Đọc biến cấu hình hệ thống `DO_OCR` (nếu là `false` thì bỏ qua OCR) và `OCR_ENGINE`.
  3. Nếu `OCR_ENGINE` cấu hình là `surya` hoặc `auto` (mặc định): Thử gọi `parse_with_surya`. Nếu gặp lỗi (thiếu thư viện, thiếu GPU...), hệ thống sẽ tự động fallback sang gọi `parse_with_vlm`.
  4. Nếu cấu hình là `vlm`, gọi trực tiếp `parse_with_vlm`.

---

### Hàm `parse_document(file_path: str) -> str`
*Đây là hàm entry point chính của toàn bộ module Parsing.*
- **Logic hoạt động:**
  1. Kiểm tra file tồn tại. Lấy phần mở rộng định dạng file (`ext`).
  2. Nếu là `.pdf`:
     - Gọi `parse_pdf_native(file_path)` để lấy văn bản.
     - **Tự động dò tìm PDF Scan:** Nếu độ dài văn bản trích xuất được ngắn hơn 100 ký tự (thường do file PDF chỉ là các ảnh quét ghép lại mà không có text layer), hệ thống tự động ghi log thông báo và chuyển hướng sang hàm OCR `parse_image_ocr(file_path)`.
  3. Nếu là `.docx` hoặc `.doc`: Gọi `parse_docx(file_path)`.
  4. Nếu là tệp ảnh (`.png`, `.jpg`, ...): Gọi trực tiếp `parse_image_ocr(file_path)`.
  5. Nếu là `.txt` hoặc `.md`: Mở đọc file trực tiếp bằng mã hóa UTF-8.
  6. Các loại tệp khác: Cố gắng đọc dưới dạng text thuần, bỏ qua các ký tự lỗi.
