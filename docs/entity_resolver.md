# Entity Resolver (`entity_resolver.py`)

## Mục tiêu
`entity_resolver.py` chịu trách nhiệm xử lý **Hậu trích xuất (Post-extraction)** để giải quyết bài toán "Rác dữ liệu" do LLM hoặc người dùng nhập sai, viết tắt. Nó là cốt lõi của tính năng chuẩn hóa thực thể trong GraphRAG.

## Tính năng chính
- **Layer 2 (Dictionary-based/Quy tắc cứng):** Ánh xạ ngay lập tức các từ viết tắt phổ biến sang chuẩn (VD: `"bk tphcm"` -> `"Ho Chi Minh City University of Technology"`, `"fast-api"` -> `"FastAPI"`).
- **Layer 3 (Fuzzy Matching):** Nếu không nằm trong Dictionary, hệ thống sẽ so khớp tương đối (Fuzzy) với danh sách các từ khóa chuẩn (`GOLDEN_RECORDS`) sử dụng thư viện `difflib`. Ngưỡng cắt mặc định là 80% (`cutoff=0.8`).
- **Dynamic Golden Records:** `EntityResolver` có khả năng nhận dữ liệu trực tiếp từ Database thông qua `dynamic_golden_records` thay vì dùng danh sách fix cứng, giúp hệ thống ngày càng "thông minh" lên khi đồ thị mở rộng.
- **Đồng bộ Anchor ID (Candidate):** Nếu Node là `Candidate` và nhận được `document_id` (UUID từ Qdrant), hệ thống sẽ ép buộc sử dụng ID này. Điều này chống rò rỉ dữ liệu khi 2 ứng viên trùng tên, và hỗ trợ Reranker truy xuất O(1) tức thì.
- **Tạo Deterministic ID:** Đối với các danh mục khác, hệ thống sinh lại ID cho Node dựa trên tên chuẩn hóa đã được tìm thấy, đảm bảo các tên viết khác nhau của cùng 1 công nghệ đều trỏ về cùng 1 Node ID.

## Vai trò trong Pipeline
Chạy ngay sau khi LLM trả kết quả về, trước khi được đưa xuống Database để đảm bảo dữ liệu trong Graph là 100% sạch.
