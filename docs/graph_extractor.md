# Graph Extractor (`graph_extractor.py`)

## Mục tiêu
`graph_extractor.py` đóng vai trò là **Người Điều Phối (Orchestrator)** của toàn bộ quá trình biến đổi văn bản thô (CV/JD) thành một Đồ thị Tri thức (Knowledge Graph) hoàn chỉnh và lưu vào database.

## Tính năng chính
1. **Giao tiếp LLM:** Sử dụng `LLMClient` để gọi API tới LLM. Bơm nội dung văn bản cùng với System Prompt (`prompts.py`) và ép LLM trả về cấu trúc JSON đúng chuẩn bằng `response_model=GraphExtractionSchema`.
2. **Post-processing (Kiểm tra tính toàn vẹn):**
   - Gọi `EntityResolver` để làm sạch và chuẩn hóa lại tên và ID của từng Node.
   - **Tự động cập nhật tham chiếu cạnh:** Nếu ID của một Node thay đổi (ví dụ do được chuẩn hóa), hệ thống sẽ tự động rà soát tất cả các Cạnh (`edges`) và đổi ID `source` / `target` tương ứng, đảm bảo tính toàn vẹn (Referential Integrity).
   - Xóa bỏ các Cạnh vô nghĩa (dangling edges) không liên kết tới bất kỳ Node nào.
3. **Tích hợp FalkorDB:** Kết nối với thể hiện của `FalkorDBGraph`. Truy vấn kho từ vựng từ đồ thị để làm giàu cho `EntityResolver`, đồng thời gọi tự động (`auto_save=True`) lưu trữ cấu trúc đã trích xuất xuống Graph Database.

## Tầm quan trọng
Là trái tim của quá trình Extract-Transform-Load (ETL) trong AI CV Matcher, đảm bảo hệ thống không bị crash do LLM halucination.
