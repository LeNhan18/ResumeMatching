# Tự động kết nối Đồ thị Tri thức (Ontology Auto-Wiring)

## 1. Vấn đề (The Problem)
Khi `GraphExtractor` bóc tách CV mới, nó chỉ tạo ra các Node và Edge mang tính sự kiện (Ví dụ: Ứng viên X làm việc tại Công ty Y, có Kỹ năng Z). Tuy nhiên, Đồ thị Tri thức cần các quy luật chung (Global Ontology) để phục vụ suy luận, ví dụ:
- Công ty Y thuộc Ngành nào?
- Kỹ năng Z thuộc Nhóm kỹ năng nào? Có kỹ năng nào thay thế được nó không?
- Ngành học A có liên quan gì tới Ngành học B không?

Nếu mỗi lần thêm CV, chúng ta bắt LLM chạy lại toàn bộ Ontology cho cả nghìn Node cũ, hệ thống sẽ sập vì quá tải và cạn kiệt Token (Chi phí O(N^2)).

---

## 2. Giải pháp 1: Incremental Wiring (Chỉ xử lý Orphan Nodes)
Thay vì nạp toàn bộ Node vào LLM, chúng ta sử dụng Cypher `WHERE NOT` để chỉ lấy ra các **Orphan Nodes** (Node mồ côi - chưa có kết nối) mới được sinh ra từ các CV vừa upload.

**Ví dụ với SkillGroup:**
```cypher
MATCH (n:Skill)
WHERE NOT (n)-[:BELONGS_TO]->(:SkillGroup)
RETURN n.id_node, n.name
```
Sau đó, chỉ nạp những "Kỹ năng mới" này cùng với "Danh sách SkillGroup có sẵn" vào LLM để nó tự phân loại. Việc này tiết kiệm 99% chi phí token.

---

## 3. Giải pháp 2: Kiến trúc Triple-Trigger (Kích hoạt 3 Lớp)
Để cân bằng giữa trải nghiệm người dùng (Real-time) và hiệu năng hệ thống (Background Processing), quá trình Wiring được quản lý bởi 3 chốt chặn:

### Lớp 1: Kích hoạt theo Ngưỡng (Threshold-driven) - Background Task
- **Vị trí:** `app.py` -> API `/api/upload_cv`
- **Cách thức:** Khi một CV được upload, API đẩy CV vào Graph, sau đó lập tức trả về `Success` cho User (không làm đóng băng UI). Chạy ngầm một `BackgroundTasks` gọi hàm Wiring với `Threshold = 10`.
- **Ý nghĩa:** Nếu hệ thống gom đủ 10 Node mồ côi, nó sẽ tự động chạy mẻ xử lý đó. Cực kỳ hiệu quả khi HR import hàng loạt (Bulk Upload).

### Lớp 2: Kích hoạt theo Thời gian (Time-driven) - APScheduler
- **Vị trí:** `app.py` -> `@app.on_event("startup")`
- **Cách thức:** Sử dụng `apscheduler` chạy ngầm trong process của FastAPI. Đúng **2:00 AM** mỗi ngày, hệ thống gọi hàm Wiring với `Threshold = 1`.
- **Ý nghĩa:** Quét sạch mọi Node rác/mồ côi cuối ngày (những CV lẻ tẻ được up lên nhưng không chạm ngưỡng Threshold 10). Không cần cài đặt `Cron` bên ngoài Linux.

### Lớp 3: Kích hoạt Tức thì (Just-In-Time) - Pre-Matching 
- **Vị trí:** `query_expansion.py` (Chuẩn bị triển khai)
- **Cách thức:** Ngay trước khi HR chạy tìm kiếm (Matching), hệ thống kiểm tra nhanh `WHERE NOT` xem có Orphan Node nào mới up lên không. Nếu có, bắt buộc xử lý nhanh (tốn 3-5s). Nếu không, bỏ qua (tốn 0.01s).
- **Ý nghĩa:** Vá lỗ hổng khi HR vừa upload CV xong và muốn tìm kiếm (Matching) ngay lập tức. Đảm bảo Graph luôn đầy đủ kiến thức 100% tại thời điểm Query.

---

## 4. Các mạng lưới Ontology được hỗ trợ (`GRAPHRAG/ontology_wire.py`)

1. **`wire_major_ontology`**: Tạo quan hệ `RELATED_MAJOR` giữa các Ngành học tương đồng (từ hẹp đến rộng).
2. **`wire_jobposition_ontology`**: Tạo quan hệ `EQUIVALENT_TO` giữa các Chức danh tương đương nhau.
3. **`wire_skill_ontology`**: Tạo quan hệ `ALTERNATIVE_TO` cho các kỹ năng có thể thay thế nhau (VD: AWS vs GCP).
4. **`wire_skillgroup_skill_ontology`**: Gom nhóm Kỹ năng `BELONGS_TO` Nhóm Kỹ năng (VD: Python -> Programming Languages).
5. **`wire_company_industry_ontology`**: Gom nhóm Công ty `BELONGS_TO` Ngành nghề (VD: VNG -> IT / Tech).
