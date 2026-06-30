# Tổng quan Giao diện người dùng (Frontend Architecture - `docs/frontend.md`)

## 1. Công nghệ sử dụng
Giao diện người dùng được phát triển bằng ngôn ngữ và framework hiện đại:
- **Core:** **React (v18+)** kết hợp với **TypeScript (TSX)** để tăng tính an toàn kiểu dữ liệu và tự động gợi ý code.
- **Build Tool:** **Vite** mang lại tốc độ biên dịch cực nhanh khi phát triển và tối ưu dung lượng bundle khi đóng gói sản phẩm.
- **Styling:** Sử dụng **Vanilla CSS** thuần (viết trong các file `App.css` và `index.css`).
- **Phong cách thiết kế:** Đậm chất **Neo-Brutalist** (Tân dã thú) cao cấp — đặc trưng bởi các đường viền đen đậm dày (`2px` hoặc `3px` solid `#1a1a1a`), đổ bóng phẳng không làm nhòe (`box-shadow: 4px 4px 0px #101010`), các màu sắc tương phản cao (vàng chanh, xanh dương, cam sữa) kết hợp với font chữ hiện đại **Space Grotesk** tạo cảm giác cực kỳ cao cấp, tối giản và chuyên nghiệp.

---

## 2. Điểm đặc biệt trong logic Frontend

### Bộ cân bằng trọng số tự động (Weight Auto-balancer)
Trong giao diện, nhà tuyển dụng có 4 thanh trượt để thay đổi trọng số chấm điểm (Kỹ năng, Kinh nghiệm, Học vấn, Kỹ năng mềm). Để đảm bảo tổng trọng số luôn bằng **100%**, Frontend cài đặt thuật toán tự động phân bổ thông minh trong hàm `handleWeightChange`:
- Khi người dùng kéo thay đổi trọng số của cột A, chênh lệch (`diff`) sẽ được chia đều hoặc chia theo tỷ lệ tương ứng cho 3 cột còn lại.
- Thuật toán tự động tính toán bù trừ phần dư làm tròn (rounding error) để đảm bảo sau mọi lượt kéo của người dùng, tổng cộng luôn luôn bằng chính xác `100` (tránh lỗi cộng số thực ra `99.99` hoặc `100.01` gây ra lỗi validate ở backend).

---

## 3. Các thành phần giao diện chính (Components & Views)
Toàn bộ logic giao diện được đóng gói tập trung trong file [App.tsx](file:///home/kiet97/ResumeMatching/frontend/src/App.tsx) và chia làm các phân vùng chức năng sau:

### 3.1. Thanh Header điều hướng
- Chứa logo thương hiệu nổi bật, hiển thị số lượng ứng viên hiện tại trong database.
- Cung cấp tab chuyển đổi giữa hai màn hình chính: **Matching Hub** (Không gian làm việc chính) và **Candidate Pool** (Kho dữ liệu ứng viên).

### 3.2. Phân vùng Hero giới thiệu
- Chứa banner giới thiệu ngắn gọn về công nghệ của hệ thống (RAG, Hybrid Search, VLM OCR, hỗ trợ tiếng Việt).
- Các nút tương tác nhanh: Tải CV, Đính kèm JD, và nút **Auto-Load Workspace CVs 📁** giúp gọi nhanh backend copy & ingest các file PDF mẫu có sẵn trong thư mục dự án lên database chỉ qua 1 click.

### 3.3. Tab Không gian làm việc: Matching Hub
*Không gian làm việc được chia làm 2 cột chính:*

#### Cột Trái: Inputs & Configs (Thiết lập đầu vào)
1. **Drag & Drop Zone (Khung tải CV):** 
   - Khu vực nét đứt hỗ trợ kéo thả file PDF/Word từ máy tính vào để tự động gọi API nạp vào database.
   - Bên dưới hiển thị danh sách tên các ứng viên đã nạp kèm nút bấm xem nhanh văn bản thô sau khi parse (`Text`) và nút xóa nhanh (`Remove`).
2. **Khung soạn thảo Job Description (JD):**
   - Hỗ trợ gõ trực tiếp văn bản JD hoặc nhấn nút **Load Sample JD 📄** để load văn bản mẫu vị trí Kỹ sư AI.
   - Hỗ trợ đính kèm tệp tin JD PDF trực tiếp.
3. **Bảng điều khiển Trọng số (Rubric Weights):**
   - 4 nút **Presets** mẫu giúp HR thiết lập nhanh trọng số theo mục tiêu tuyển dụng:
     - *Balanced ⚖️:* Cân bằng (40% Skills, 30% Exp, 15% Edu, 15% Culture).
     - *Tech Heavy 🛠️:* Tập trung công nghệ (60% Skills, 20% Exp, 10% Edu, 10% Culture).
     - *Tenure & Lead 🏢:* Tập trung quản lý/thâm niên (30% Skills, 50% Exp, 10% Edu, 10% Culture).
     - *Junior & Academic 🎓:* Ưu tiên học thuật (35% Skills, 15% Exp, 30% Edu, 20% Culture).
   - 4 thanh trượt tùy chỉnh thủ công có tính năng tự động cân bằng như đã nêu ở phần logic.
   - Nút **Evaluate Candidates** màu xanh nổi bật để gửi yêu cầu so khớp sang Backend.

#### Cột Phải: Bảng điều khiển kết quả xếp hạng (Evaluation Dashboard)
Hiển thị danh sách ứng viên đã được xếp hạng theo thứ tự điểm số giảm dần:
- Mỗi ứng viên hiển thị dạng thẻ card nổi khối, có màu badge điểm số tương ứng mức độ phù hợp: Xanh lá (Cao: >= 80%), Vàng (Trung bình: >= 50%), Đỏ (Thấp: < 50%).
- Hiển thị nhanh cờ kiểm duyệt Hard-match (Đạt/Không đạt điều kiện cứng) và cờ chứng chỉ tiếng Anh.
- **Khung mở rộng thông tin chi tiết (khi click vào card):**
  - **Biểu đồ tiến trình (Progress Bars):** Minh họa điểm số chi tiết của 4 danh mục so với trọng số tương ứng.
  - **Checklist điều kiện cứng:** Hiển thị chi tiết trạng thái kiểm duyệt (Số năm kinh nghiệm tính toán được so với yêu cầu, Tỷ lệ đáp ứng kỹ năng bắt buộc, Học vị, Chứng chỉ tiếng Anh, Trạng thái đi làm doanh nghiệp).
  - **Hộp thoại Strengths & Missing Skills:** Hiển thị trực quan các thẻ tag điểm mạnh (màu xanh lá) và công nghệ còn thiếu (màu đỏ) của ứng viên.
  - **Accordion Qualitative Assessment:** Hiển thị bài phân tích đánh giá định tính chi tiết bằng tiếng Việt do LLM lập luận.

### 3.4. Tab Quản lý ứng viên: Candidate Pool
- Hiển thị danh sách toàn bộ hồ sơ ứng viên dưới dạng thẻ chi tiết.
- Show đầy đủ thông tin liên lạc (Email, Phone), nhóm ngành nghề.
- Liệt kê toàn bộ các kỹ năng đã trích xuất được dưới dạng thẻ tag.
- Render dòng thời gian lịch sử làm việc (Experience Timeline) hiển thị rõ chức danh, tên công ty, thời gian công tác và các công nghệ sử dụng trong từng công việc.
- Cung cấp nút xóa vĩnh viễn ứng viên khỏi DB và ổ đĩa server.

### 3.5. Modal xem văn bản thô
- Một popup overlay tối giản hiển thị font chữ monospaced (`Courier New`) trình bày toàn bộ đoạn văn bản gốc trích xuất từ file tài liệu của ứng viên, giúp nhà tuyển dụng kiểm tra đối chiếu tính chính xác của bộ lọc OCR khi cần thiết.
