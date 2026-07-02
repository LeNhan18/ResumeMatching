# Graph Schemas (`graph_schemas.py`)

## Mục tiêu
`graph_schemas.py` chứa bộ cấu trúc dữ liệu nghiêm ngặt (Data Schemas) được định nghĩa bằng thư viện **Pydantic**. Đây là "xương sống" ép các LLMs như OpenAI, Gemini, Claude phải trả về dữ liệu đúng định dạng JSON.

## Chi tiết các thành phần
1. **Edge Properties (Thuộc tính cạnh):**
   - Chứa thông tin bổ sung cho mỗi Relationship.
   - Ví dụ: `WorkedAtProperties` chứa vị trí, thời gian (tháng). `StudiedAtProperties` chứa bằng cấp, GPA.
2. **ExtractedNode (Thực thể Node):**
   - Quy định Node bắt buộc phải có `id_node`, `name` và nhãn `labels` (chọn từ 11 nhãn, bao gồm các nhãn hệ thống như `Candidate` và các nhãn ontology mở rộng như `JobTitle`, `Major`).
   - Cung cấp hàng loạt fields không bắt buộc (Optional) như `phone`, `summary`... LLM sẽ tự động bóc tách và điền vào nếu có.
3. **ExtractedEdge (Mối quan hệ Edge):**
   - Ràng buộc quan hệ qua `source`, `target` (ID Node nguồn, đích) và loại quan hệ `edge_type` (chọn 1 trong 13 loại như `WORKED_AT`, `REQUIRES_SKILL`, `EQUIVALENT_TO`, `RELATED_MAJOR`).
   - Có cơ chế nhúng trực tiếp Edge Properties vào bên trong dựa theo loại Relationship.
4. **GraphExtractionSchema (Schema Tổng):**
   - Đóng gói toàn bộ `nodes` và `edges` thành một Schema gốc duy nhất để gửi cho LLM (Structured Output).

## Vai trò cốt lõi
Nếu không có file này, LLM sẽ sinh ra JSON với key/value tùy tiện, gây sụp đổ hệ thống lúc đưa dữ liệu vào Graph. Nó chính là "lá chắn" bảo vệ hệ thống khỏi sự thiếu ổn định của LLM.

## Mô hình Biểu diễn kép (Dual-Representation Pattern)
Hệ thống áp dụng mô hình biểu diễn kép đối với Chức danh (JobPosition) và Ngành học (Major) để giải quyết bài toán "Mất liên kết lịch sử" (Loss of Context):
- **Trục Sự kiện (Fact/History):** Các thuộc tính `position` và `major` vẫn được lưu dưới dạng text property bên trong cạnh `WORKED_AT` và `STUDIED_AT` để ghi nhận chính xác ứng viên làm vị trí đó ở công ty nào và trong bao lâu.
- **Trục Mạng lưới (Ontology):** Trích xuất thêm các Node độc lập `JobPosition` và `Major` kết nối trực tiếp với Candidate qua các cạnh `HELD_POSITION` và `STUDIED_MAJOR`. Các Node này đóng vai trò như Từ điển ngành nghề, cho phép chạy các thuật toán Query Expansion và Graph Reasoning để móc nối các Node tương đương (`EQUIVALENT_TO`, `RELATED_MAJOR`) mà không làm hỏng dòng thời gian lịch sử.
