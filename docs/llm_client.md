# Tài liệu kỹ thuật: LLM Client (`LLM/client.py`)

## 1. Tổng quan
File `LLM/client.py` chịu trách nhiệm giao tiếp với LLM API (mặc định hỗ trợ OpenAI và OpenRouter). Nó đóng gói toàn bộ logic gọi mô hình ngôn ngữ lớn để sinh văn bản thông thường (text generation) hoặc trích xuất dữ liệu có cấu trúc (structured output) theo schema định sẵn bằng Pydantic. 

Đặc biệt, file này hỗ trợ cơ chế **Mock Mode** (chạy giả lập không cần API Key) giúp hệ thống vẫn chạy thử nghiệm được ở môi trường local sandbox khi không cấu hình API Key.

---

## 2. Các thư viện sử dụng
- `pydantic` (hỗ trợ định nghĩa schema, validate dữ liệu).
- `openai` (thư viện chính để call API GPT/Gemini/Claude qua giao diện tương thích OpenAI).
- `dotenv` (load các biến môi trường từ file `.env`).

---

## 3. Lớp `LLMClient`

### Hàm khởi tạo `__init__(self)`
- **Nhiệm vụ:** Đọc các biến cấu hình từ môi trường (`LLM_PROVIDER`, `API_KEY_OPENROUTER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_NAME`, `OPENAI_MODEL`).
- **Logic hoạt động:**
  - Nếu `LLM_PROVIDER` là `openrouter`: Đọc API Key từ các nguồn ưu tiên tương ứng (`API_KEY_OPENROUTER` -> `LLM_API_KEY` -> `OPENAI_API_KEY`). Base URL mặc định là `https://openrouter.ai/api/v1` và model là `google/gemini-2.5-flash` nếu không cấu hình khác.
  - Ngược lại: Đọc key tiêu chuẩn, base URL từ `LLM_BASE_URL` và sử dụng model `gpt-4o-mini` làm mặc định.
  - Khởi tạo client của OpenAI: `OpenAI(api_key=..., base_url=...)`.
  - Nếu thiếu API Key, chương trình sẽ log cảnh báo và tự động chuyển sang chế độ **MOCK** (tự trả về dữ liệu giả lập có cấu trúc đúng định dạng để test code).

---

### Phương thức `is_configured(self) -> bool`
- **Đầu ra:** `True` nếu client của OpenAI đã được khởi tạo thành công (tức là đã cấu hình API key), ngược lại trả về `False`.

---

### Phương thức `generate_text(self, prompt: str, system_prompt: str = "", temperature: float = 0.2) -> str`
- **Tham số:**
  - `prompt`: Nội dung câu hỏi từ user.
  - `system_prompt` (tùy chọn): Định nghĩa vai trò hệ thống cho LLM.
  - `temperature`: Tham số kiểm soát tính sáng tạo (mặc định thấp `0.2` để giữ tính nhất quán).
- **Đầu ra:** Nội dung phản hồi dạng chuỗi ký tự (`str`).
- **Logic:** Gửi danh sách messages đến endpoint `client.chat.completions.create` và trả về `.choices[0].message.content`. Nếu chưa cấu hình API Key, nó sẽ tự động trả về chuỗi thông báo Mock.

---

### Phương thức `generate_structured(self, prompt: str, response_model: Type[T], system_prompt: str = "", temperature: float = 0.1) -> T`
*Đây là phương thức cốt lõi dùng cho trích xuất thông tin CV/JD ở Layer 3 và đánh giá định lượng ở Layer 6.*
- **Tham số:**
  - `prompt`: Văn bản đầu vào cần trích xuất thông tin.
  - `response_model`: Một lớp kế thừa từ `pydantic.BaseModel` đại diện cho cấu trúc JSON mong muốn nhận được.
  - `system_prompt` (tùy chọn): System prompt hướng dẫn LLM.
  - `temperature`: Mặc định cực thấp `0.1` để tối đa hóa tính chính xác của cấu trúc dữ liệu.
- **Đầu ra:** Một thực thể (instance) của lớp `response_model` chứa dữ liệu đã được validate.
- **Logic hoạt động:**
  1. **Bước Kiểm Tra Mock:** Nếu chưa cấu hình API key, gọi `_generate_mock_instance(response_model)` để sinh dữ liệu giả lập tương ứng.
  2. **Phương pháp 1 (Native Structured Outputs):** Sử dụng API `.beta.chat.completions.parse` của OpenAI. Đây là tính năng giúp cam kết LLM luôn xuất ra đúng định dạng JSON Schema mà Pydantic yêu cầu mà không bị thừa ký tự hoặc lỗi cú pháp.
  3. **Phương pháp 2 (Fallback JSON Mode):** Nếu phương pháp 1 lỗi hoặc mô hình/endpoint không hỗ trợ (ví dụ khi chạy qua một số model OpenRouter cũ), hệ thống sẽ fallback:
     - Nhúng trực tiếp JSON schema của Pydantic model vào prompt qua `model.model_json_schema()`.
     - Gọi API thông thường với tham số `response_format={"type": "json_object"}`.
     - Sau khi nhận chuỗi text, tiến hành bóc tách các ký tự markdown block (ví dụ: ` ```json `), rồi gọi `response_model.model_validate_json(content)` để ép kiểu và trả về dữ liệu chuẩn.

---

### Phương thức `_generate_mock_instance(self, model_class: Type[T]) -> T`
- **Nhiệm vụ:** Tự động tạo dữ liệu giả lập cho các Pydantic class (`CVSchema`, `JDSchema`, `ScoringResult`) khi API Key không tồn tại.
- **Logic hoạt động:**
  - Duyệt qua toàn bộ các thuộc tính (fields) của Pydantic class để xác định kiểu dữ liệu (`str`, `float`, `int`, `list`, `dict`).
  - Điền giá trị mặc định trống (như chuỗi rỗng, mảng rỗng, giá trị 0.0) dựa trên phân loại trường.
  - Thiết lập cứng một số thông tin trực quan cho các lớp đặc thù:
    - Nếu là `CVSchema`: Tạo ứng viên tên "Nguyen Van A" có kỹ năng Python, Docker, SQL, Git và 1 công việc tại "Fintech Corp".
    - Nếu là `JDSchema`: Tạo JD "Backend Engineer" yêu cầu kinh nghiệm 2.0 năm.
    - Nếu là `ScoringResult`: Trả về kết quả đánh giá giả lập với `match_score=50.0`.
  - Trả về đối tượng Pydantic hoàn chỉnh đã qua validate.
