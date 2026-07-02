# Prompts (`prompts.py`)

## Mục tiêu
`prompts.py` đóng vai trò là "Bộ Luật" hướng dẫn LLM cách hoạt động. Nó chứa các System Prompt cực kỳ chi tiết, ép LLM phải hành xử như một kỹ sư trích xuất Đồ thị tri thức (Knowledge Graph) chuyên nghiệp cho lĩnh vực Nhân sự.

## Nội dung chi tiết
File chứa 2 Prompt riêng biệt cho 2 bài toán:
1. **EXTRACT_CV_PROMPT_SYSTEM (Trích xuất ứng viên):**
   - Hướng dẫn LLM cách tạo các ID ổn định và slugified (ví dụ: `cand_nguyen_van_a`).
   - Yêu cầu bắt buộc tạo đúng MỘT `Candidate` node đóng vai trò trung tâm (Root node).
   - Yêu cầu bóc tách từng chứng chỉ ngôn ngữ (IELTS, TOEIC) đến chứng chỉ công nghệ, và cách liên kết chúng qua `EARNED` và `VALIDATES_SKILL`.
2. **EXTRACT_JOB_PROMPT_SYSTEM (Trích xuất công việc - JD):**
   - Chỉ định `Job` là node trung tâm.
   - Đưa ra logic đánh giá `is_mandatory` (Bắt buộc hay Không bắt buộc) đối với các kỹ năng.
   - Tự động nhận diện công nghệ thay thế nhau (Ví dụ: AWS hoặc GCP) và tạo Edge `ALTERNATIVE_TO` để kết nối chúng.

## Điểm nhấn
Cả hai prompt đều nhấn mạnh mạnh mẽ quy tắc **Referential Integrity** (Tính toàn vẹn tham chiếu): Tuyệt đối không sinh ra Cạnh (`Edge`) nối tới một Node chưa từng được định nghĩa. Đây là mấu chốt để Graph DB không bị lỗi tham chiếu khi Insert.
