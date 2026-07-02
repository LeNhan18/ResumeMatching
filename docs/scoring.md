# Tài liệu kỹ thuật: LLM Evaluation & Scoring (`RAG/scoring.py`)

## 1. Tổng quan
File `RAG/scoring.py` chứa định nghĩa lớp `LLMScorer` thực thi nhiệm vụ tại **Layer 6 — LLM Evaluation & Scoring**. Đây là tầng cuối cùng trong pipeline kết hợp sức mạnh phân tích định tính (qualitative) của LLM và tính toán định lượng (quantitative) bằng mã nguồn Python thuần để tính ra điểm số phù hợp tổng hợp (`match_score`) đảm bảo tính chính xác, khách quan và dễ giải trình.

---

## 2. Lớp `LLMScorer`

### 2.1. Khởi tạo `__init__(self, llm_client: LLMClient)`
- Nhận đối tượng `llm_client` để thực hiện các cuộc gọi API có cấu trúc tới LLM.

### 2.2. Phương thức `score_candidate`
```python
def score_candidate(
    self, 
    cv: CVSchema, 
    jd: JDSchema, 
    hard_match_res: Dict[str, Any], 
    soft_match_score: float, 
    weights: ScoringWeights,
    graph_insights: list[str] = None
) -> ScoringResult:
```
- **Tham số đầu vào:**
  - `cv`: Thông tin chi tiết đã cấu trúc hóa của ứng viên.
  - `jd`: Yêu cầu cấu trúc hóa của tin tuyển dụng.
  - `hard_match_res`: Kết quả kiểm duyệt các điều kiện cứng từ Layer 5.
  - `soft_match_score`: Điểm tương đồng ngữ nghĩa thu được từ Layer 5 (trong khoảng `[0.0, 1.0]`).
  - `weights`: Tập trọng số cấu hình chấm điểm (ví dụ: Kỹ năng 40%, Kinh nghiệm 30%...).
  - `graph_insights`: Mảng chứa các câu giải thích từ GraphDB (Ví dụ: "Sở hữu ReactJS thay thế cho VueJS"). Dùng để hỗ trợ LLM suy luận Explainable AI (XAI). Mặc định là `None` (khi chạy Single Match).
- **Đầu ra:** Trả về đối tượng `ScoringResult` chứa điểm tổng kết, điểm thành phần, danh sách ưu/nhược điểm và văn bản giải trình lý do chấm.

---

## 3. Quy trình hoạt động chi tiết

### Bước 1: Tổng hợp ngữ cảnh và xây dựng Prompt
Hệ thống thu thập toàn bộ dữ liệu từ các bước trước đó để tạo thành một Prompt cực kỳ chi tiết gửi đến LLM, bao gồm:
1. **Thông tin JD:** Tên vị trí, yêu cầu kỹ năng, học vấn, số năm kinh nghiệm tối thiểu.
2. **Thông tin CV:** Tóm tắt hồ sơ, học vị đại học, danh sách kỹ năng, chứng chỉ và ngoại ngữ.
3. **Lịch sử công tác:** Liệt kê chi tiết từng công ty ứng viên đã làm, vị trí, thời gian công tác và các công nghệ sử dụng.
4. **Các chỉ số đo đạc từ Layer 5:** Số năm kinh nghiệm liên quan tính toán bằng code, trạng thái pass/fail các điều kiện cứng, độ tương đồng ngữ nghĩa (soft-match score), trạng thái chứng chỉ tiếng Anh và số năm đi làm doanh nghiệp thực tế.

---

### Bước 2: Thiết lập quy tắc chấm điểm nghiêm ngặt (System Prompt)
System Prompt định nghĩa vai trò của LLM là một Chuyên gia Thẩm định Nhân sự AI và áp đặt các luật bắt buộc:
- **Ngôn ngữ đầu ra:** Toàn bộ phần văn bản giải trình, điểm mạnh, kỹ năng thiếu **phải viết bằng tiếng Việt**. Tuy nhiên, các thuật ngữ kỹ thuật phải giữ nguyên gốc tiếng Anh, không được dịch thô.
- **Quy tắc ưu tiên kinh nghiệm doanh nghiệp (Corporate Experience):** Đây là quy tắc cực kỳ nghiêm ngặt nhằm tránh việc ứng viên có nhiều dự án cá nhân/học tập nhưng chưa từng đi làm thực tế được điểm cao. LLM bắt buộc phải phạt điểm dưới `50/100` ở mục kinh nghiệm (`experience`) đối với những hồ sơ chỉ có dự án cá nhân hoặc đồ án tốt nghiệp.
- **Quy tắc ưu tiên chứng chỉ tiếng Anh (English Certificates):** Các hồ sơ có chứng chỉ tiếng Anh quốc tế được ưu tiên cộng thêm điểm thưởng và ghi nhận trực tiếp vào danh sách điểm mạnh.
- **Quy tắc Explainable AI (XAI RULE):** Nếu có mảng `graph_insights` truyền vào, Prompt sẽ chèn thêm khối kiến thức Đồ thị (Layer 5.5). Khi đó, System Prompt sẽ ra lệnh **không được trừ điểm** hoặc liệt kê kỹ năng vào `missing_skills` nếu Đồ thị đã ghi nhận có kỹ năng thay thế/tương đương. LLM phải sử dụng các Insight này để viết lời giải thích bênh vực cho ứng viên.
- **Chain-of-Thought (COT RULE):** Ép LLM phải suy nghĩ từng bước (Think step-by-step), viết ra phân tích lý luận chi tiết *trước khi* được phép đưa ra con số điểm tương ứng.

---

### Bước 3: Định nghĩa cấu trúc phản hồi bằng Chain-of-Thought (CoT)
Bên trong hàm `score_candidate`, hệ thống thiết lập một Pydantic model nội bộ là `LLMScoringResponse` để định hình JSON xuất ra từ LLM. Để giải quyết triệt để lỗi "ảo giác" (điểm số không khớp với nhận xét) mà không tốn thêm token gọi mô hình Critic, hệ thống áp dụng Constraint CoT bằng cách chẻ nhỏ trường `reasoning` và đè lên trên các trường điểm:

- `reasoning_skills` (str): Phân tích kỹ năng.
- `skills` (float): Điểm kỹ năng (được sinh ra *sau khi* viết phân tích).
- `reasoning_experience` (str) & `experience` (float)
- `reasoning_education` (str) & `education` (float)
- `reasoning_culture` (str) & `culture_fit` (float)
- `missing_skills` (list[str])
- `strengths` (list[str])

Cách thiết kế Schema cắt lớp từ trên xuống dưới này ép mô hình ngôn ngữ (Transformer) phải biện luận logic xong xuôi mới được quyền xuất ra con số điểm, giúp điểm số đạt độ tin cậy và khách quan cao nhất. Các đoạn lý do rời rạc sau đó được code Python gộp lại thành một chuỗi `reasoning_combined` duy nhất để trả về cho Frontend.

---

### Bước 4: Tính toán điểm số tổng hợp (Deterministic Weighted Scoring)
Sau khi nhận kết quả chấm điểm các danh mục thành phần từ LLM, **Python sẽ đứng ra thực hiện phép tính điểm tổng kết bằng code thuần**, tuyệt đối không để LLM tự tính toán nhằm tránh lỗi logic toán học và đảm bảo tính nhất quán:
$$\text{match\_score} = (\text{skills\_score} \times \text{weights.skills}) + (\text{experience\_score} \times \text{weights.experience}) + (\text{education\_score} \times \text{weights.education}) + (\text{culture\_score} \times \text{weights.culture\_fit})$$

Điểm số sau đó được làm tròn đến chữ số thập phân thứ nhất và giới hạn chặt chẽ trong khoảng `[0.0, 100.0]`.

---

### Bước 5: Cơ chế dự phòng lỗi (Fallback Mode)
Nếu cuộc gọi API tới LLM bị gián đoạn hoặc trả về lỗi, hệ thống sẽ tự động kích hoạt chế độ Graceful Fallback:
- Trả về điểm mặc định cho các mục là `50.0`.
- Lấy danh sách kỹ năng thiếu trực tiếp từ kết quả Hard-match của Layer 5.
- Ghi nhận phần giải trình (`reasoning`) chứa thông báo lỗi để HR biết hệ thống đang tạm thời hoạt động ở chế độ dự phòng.
