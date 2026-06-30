# Tài liệu kỹ thuật: Data Schemas & Rubric Config (`RAG/schemas.py`)

## 1. Tổng quan
File `RAG/schemas.py` chứa định nghĩa các cấu trúc dữ liệu chính trong toàn bộ hệ thống bằng thư viện **Pydantic**. Việc sử dụng Pydantic giúp tự động hóa khâu kiểm tra kiểu dữ liệu (data validation), ép kiểu chính xác khi nhận phản hồi JSON từ LLM ở Layer 3 và Layer 6, đồng thời cung cấp cơ chế kiểm duyệt dữ liệu đầu vào (Guardrails) cho hệ trọng số chấm điểm.

---

## 2. Các lớp dữ liệu (Schemas) chi tiết

### 2.1. Lớp `WorkExperience`
*Mô tả cấu trúc cho từng mốc lịch sử làm việc của ứng viên.*
- **Các trường thông tin:**
  - `company` (str): Tên công ty hoặc tổ chức làm việc.
  - `position` (str): Chức danh công việc / Vị trí đảm nhiệm.
  - `start_date` (str): Ngày bắt đầu (định dạng chuẩn hóa thường là `YYYY-MM` hoặc `YYYY`).
  - `end_date` (Optional[str], mặc định `None`): Ngày kết thúc (hoặc chuỗi `'Present'` nếu đang tiếp tục công tác).
  - `skills_used` (List[str]): Danh sách các kỹ năng, công nghệ cụ thể được sử dụng trong công việc này.
  - `seniority_level` (str, mặc định `"Mid"`): Cấp bậc của vị trí (e.g. Junior, Mid, Senior, Lead, Manager).
  - `experience_type` (str, mặc định `"Corporate"`): Phân loại loại hình kinh nghiệm. Đây là một trường cực kỳ quan trọng để phục vụ chấm điểm Hard-match và định lượng. Các giá trị hợp lệ bao gồm:
    - `"Corporate"` (Làm việc chính thức/hợp đồng tại công ty).
    - `"Internship"` (Thực tập sinh).
    - `"Freelance"` (Làm việc tự do).
    - `"Personal Project"` (Dự án cá nhân tự nghiên cứu).
    - `"Academic Project"` (Đồ án tốt nghiệp, bài tập lớn tại trường học).
  - `description` (Optional[str]): Mô tả chi tiết về trách nhiệm và các thành tích đạt được trong công việc.

---

### 2.2. Lớp `EducationInfo`
*Mô tả thông tin học vấn của ứng viên.*
- **Các trường thông tin:**
  - `school` (str): Tên trường học, đại học hoặc học viện.
  - `degree` (Optional[str]): Loại bằng cấp (Bachelor/Cử nhân, Master/Thạc sĩ, PhD/Tiến sĩ, Associate/Cao đẳng).
  - `major` (Optional[str]): Chuyên ngành học.
  - `grad_year` (Optional[str]): Năm tốt nghiệp.

---

### 2.3. Lớp `CVSchema`
*Mô tả cấu trúc hoàn chỉnh của một CV sau khi trích xuất dữ liệu có cấu trúc từ LLM.*
- **Các trường thông tin:**
  - `name` (str): Họ và tên đầy đủ của ứng viên.
  - `email`, `phone` (Optional[str]): Thông tin liên hệ.
  - `skills` (List[str]): Danh sách các kỹ năng chung được liệt kê trong CV.
  - `experience` (List[WorkExperience]): Danh sách lịch sử làm việc sắp xếp theo thứ tự thời gian.
  - `education` (List[EducationInfo]): Danh sách lịch sử học vấn.
  - `certs` (List[str]): Các chứng chỉ đạt được.
  - `languages` (List[str]): Các ngôn ngữ sử dụng được.
  - `summary` (Optional[str]): Tóm tắt mục tiêu nghề nghiệp/giới thiệu bản thân.
  - `industry` (Optional[str]): Ngành nghề chính của ứng viên (ví dụ: IT, Banking, Healthcare).
  - `domain_specific_fields` (Dict[str, str]): Cấu trúc dạng key-value linh hoạt để lưu trữ các thông tin đặc thù theo từng ngành nếu có.

---

### 2.4. Lớp `JDSchema`
*Mô tả cấu trúc thông tin yêu cầu của tin tuyển dụng (Job Description).*
- **Các trường thông tin:**
  - `position` (str): Tên vị trí tuyển dụng mục tiêu.
  - `required_skills` (List[str]): Danh sách kỹ năng bắt buộc (essential skills).
  - `nice_to_have` (List[str]): Danh sách kỹ năng ưu tiên hoặc bổ trợ (nice-to-have).
  - `min_exp_years` (float): Số năm kinh nghiệm tối thiểu yêu cầu (ví dụ: `3.0`).
  - `level` (str): Cấp bậc yêu cầu (Junior, Mid, Senior...).
  - `domain` (str): Lĩnh vực chuyên môn tập trung (e.g. Backend, Frontend, DevOps, Sales).
  - `industry` (str): Nhóm ngành (IT, Retail, Finance...).
  - `education_requirement` (Optional[str]): Yêu cầu tối thiểu về trình độ học vấn.
  - `location` (Optional[str]): Địa điểm làm việc.

---

### 2.5. Lớp `ScoringWeights` (Rubric Configuration Guardrail)
*Định nghĩa hệ trọng số phân bổ cho các tiêu chí chấm điểm.*
- **Các trường thông tin:**
  - `skills` (float, mặc định `0.4`): Trọng số của tiêu chí kỹ năng. Phải nằm trong khoảng `[0.2, 0.6]`.
  - `experience` (float, mặc định `0.3`): Trọng số của tiêu chí kinh nghiệm & thời gian công tác. Phải nằm trong khoảng `[0.1, 0.5]`.
  - `education` (float, mặc định `0.15`): Trọng số của trình độ học vấn. Phải nằm trong khoảng `[0.0, 0.3]`.
  - `culture_fit` (float, mặc định `0.15`): Trọng số của kỹ năng mềm/độ hòa hợp văn hóa. Phải nằm trong khoảng `[0.0, 0.3]`.
- **Cơ chế Guardrail (`check_sum` model validator):**
  Phương thức validator chạy sau khi khởi tạo (`mode="after"`) thực hiện tính tổng 4 trọng số trên. Tổng này phải nằm trong biên sai số hẹp xung quanh 100% (`0.95 <= total <= 1.05`), nếu không sẽ ném ra lỗi `ValueError`. Điều này ngăn cản người dùng cấu hình các trọng số vô lý làm sai lệch kết quả xếp hạng.

---

### 2.6. Lớp `ScoringBreakdown`
*Lưu trữ điểm số chi tiết (từ 0 đến 100) cho từng danh mục đánh giá.*
- **Các trường thông tin:** `skills` (kỹ năng), `experience` (kinh nghiệm), `education` (học vấn), `culture_fit` (độ phù hợp văn hóa).

---

### 2.7. Lớp `ScoringResult`
*Kết quả đánh giá chất lượng cuối cùng trả ra bởi LLM Scorer.*
- **Các trường thông tin:**
  - `match_score` (float): Điểm số phù hợp tổng hợp (từ 0 đến 100) tính toán bằng công thức nhân trọng số.
  - `breakdown` (ScoringBreakdown): Điểm số chi tiết cho từng cột tiêu chí.
  - `missing_skills` (List[str]): Các kỹ năng yêu cầu trong JD nhưng thiếu hoặc yếu trong CV ứng viên.
  - `strengths` (List[str]): Các điểm cộng, điểm mạnh nổi bật của ứng viên.
  - `reasoning` (str): Bài phân tích định tính chi tiết bằng văn bản tiếng Việt làm cơ sở cho điểm số được chấm.
