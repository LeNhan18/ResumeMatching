# Kế Hoạch Triển Khai Query Expansion Bằng Đồ Thị Tri Thức (FalkorDB)

## 1. Mục Tiêu Chiến Lược
Mục tiêu của giai đoạn này là giải quyết bài toán "bất đồng ngôn ngữ" giữa JD (Mô tả công việc) do HR viết và CV (Sơ yếu lý lịch) do ứng viên viết. Bằng cách sử dụng Đồ thị tri thức (FalkorDB) đã được xây dựng, chúng ta sẽ tự động mở rộng câu truy vấn gốc của người dùng thành một **Câu truy vấn siêu cấp (Enriched Super-Query)**.

Câu truy vấn mở rộng này sẽ giúp tối ưu hóa triệt để tầng tìm kiếm lai (Hybrid Search) trên cơ sở dữ liệu vector (Qdrant) - đặc biệt là để tăng điểm cho tầng Sparse Search (BM25).

---

## 2. Giải Đáp Các Vấn Đề Kiến Trúc Cốt Lõi (Dựa trên câu hỏi của bạn)

### A. Về việc tạo thêm Node `JobTitle` hay dùng chung Node `Job`?
**Câu hỏi của bạn:** *Có nhất thiết phải thêm node `JobTitle` không vì node `Job` đã có trường `name` và `position`?*

**Phân tích & Lựa chọn:**
Bạn hoàn toàn có thể dùng Node `Job` hiện tại để link lại với nhau nhằm tiết kiệm việc sửa schema, nhưng về mặt **Graph Semantics (Ngữ nghĩa đồ thị)** về lâu dài, việc tách riêng Node `JobTitle` là bắt buộc vì:
- **Node `Job` là một Thực thể cụ thể (Instance/Document):** Nó đại diện cho 1 tin tuyển dụng cụ thể tại 1 thời điểm cụ thể (VD: "Tuyển Senior Backend Developer tại Momo tháng 6/2026"). Nó mang các đặc tính như `min_exp_years`, `location`.
- **Node `JobTitle` là một Thực thể khái niệm (Ontology Class):** Nó đại diện cho khái niệm trừu tượng "Backend Developer". Hàng ngàn tin tuyển dụng (Node `Job`) và hàng ngàn ứng viên (Node `Candidate`) có thể cùng trỏ về một khái niệm `JobTitle` này.
- **Hệ quả:** Nếu bạn nối 2 tin tuyển dụng (`Job`) bằng `EQUIVALENT_TO`, đồ thị sẽ rất rối loạn (tin tuyển dụng của Momo lại tương đương tin tuyển dụng của VNG?). Nhưng nếu nối 2 khái niệm `JobTitle` ("Backend Developer" tương đương "Server-side Engineer") thì đồ thị biến thành một "Từ điển ngành tuyển dụng" cực kỳ mạnh mẽ.
=> **Kết luận:** Nên tách riêng `JobTitle` (hoặc Role) để đồ thị hỗ trợ khả năng suy luận (Reasoning) tốt nhất.

### B. Tiếp nhận truy vấn JD: Bóc tách bằng Graph hay LLM thường? Có đưa JD vào Graph không?
**Câu hỏi của bạn:** *JD sẽ được bóc tách bằng Graph Extractor hay LLM thông thường? Có đưa JD vào Graph không?*

**Phân tích & Lựa chọn:**
Phải phân tách rõ giữa luồng **Lưu trữ (Ingestion)** và luồng **Tìm kiếm (Search/Retrieval)**:
- **Trong luồng Tìm kiếm (Real-time): KHÔNG CẦN đưa JD vào Graph bằng Graph Extractor.** 
  - Graph Extractor chạy khá nặng và tốn kém. Tại thời điểm HR tải JD lên để tìm ứng viên, hệ thống cần phản hồi trong vài giây.
  - Bạn chỉ cần dùng **LLM Extractor thông thường (kết hợp Structured Output/Pydantic)** để trích xuất nhanh JD thành cục JSON chứa các từ khóa trọng tâm: `position`, `industry`, `required_skills`, `major`.
  - Sau đó, lấy các từ khóa JSON này làm biến đầu vào (`$jd_position`, `$jd_industry`...) ném vào FalkorDB để thực thi các câu lệnh Cypher (Query Expansion). Đồ thị tri thức ở đây đóng vai trò là "Từ điển" để bạn tra cứu từ đồng nghĩa, chứ không phải là nơi lưu trữ JD truy vấn.
- **Trong luồng Ingestion (Background Task):**
  - Về sau, nếu HR muốn lưu JD này làm dữ liệu lịch sử, một background job sẽ kích hoạt `Graph Extractor` bóc tách sâu JD này để bổ sung các quan hệ (Node `Job`, `REQUIRES_SKILL`...) vào FalkorDB, giúp "huấn luyện" đồ thị ngày càng giàu dữ liệu hơn.

---

## 3. Khai Thác Sức Mạnh Đồ Thị: 5 Chiều Không Gian Mở Rộng

Với 4 chiều hiện tại là rất xuất sắc, nhưng dựa vào kiến trúc `graph_schemas.py` đang có (các trường về học vấn, dự án), hệ thống hoàn toàn có thể vươn tới **5 chiều không gian** để vét cạn năng lực đồ thị.

### Chiều không gian 1: Mở rộng chức danh (Job Title Ontology)
- **Bài toán:** Ứng viên ghi chức danh khác với JD (`Backend Engineer` vs `Python Developer`).
- **Truy vấn Cypher (Dự kiến - Yêu cầu thêm Node JobTitle):**
  ```cypher
  MATCH (j:JobTitle {name: $jd_position})-[:EQUIVALENT_TO]-(alt:JobTitle)
  RETURN collect(alt.name) AS equivalent_titles
  ```

### Chiều không gian 2: Hệ sinh thái ngành & Công ty đối thủ (Industry & Competitor Mapping)
- **Bài toán:** Kéo được CV của ứng viên làm ở công ty đối thủ (không thèm ghi tên ngành).
- **Truy vấn Cypher (Đã hỗ trợ sẵn trong schema):**
  ```cypher
  MATCH (i:Industry {name: $jd_industry})<-[:BELONGS_TO]-(comp:Company)
  RETURN collect(comp.name) AS competitor_companies
  ```

### Chiều không gian 3: Chứng chỉ bảo chứng năng lực (Certification Expansion)
- **Bài toán:** Ứng viên ghi "AWS Solutions Architect" thay vì gõ chữ "AWS".
- **Truy vấn Cypher (Đã hỗ trợ sẵn trong schema):**
  ```cypher
  MATCH (s:Skill)-[:VALIDATES_SKILL]-(cert:Certificate)
  WHERE s.name IN $jd_skills
  RETURN collect(cert.name) AS related_certificates
  ```

### Chiều không gian 4: Kỹ năng chuyên môn (Mở rộng Ngang & Dọc)
- **Bài toán:** Bao quát các công nghệ tương đương hoặc thuộc cùng họ công nghệ.
- **Truy vấn Cypher (Đã hỗ trợ sẵn trong schema):**
  ```cypher
  MATCH (s:Skill)-[:ALTERNATIVE_TO]-(alt:Skill)
  WHERE s.name IN $jd_skills
  RETURN collect(alt.name) AS alternative_skills
  ```

### Chiều không gian 5: Bối cảnh Đào tạo (Major & Degree Context)
- **Bài toán:** JD yêu cầu bằng "Khoa học máy tính" (Computer Science). Nếu dùng Keyword match, CV ghi "Công nghệ thông tin", "Toán Tin", hay "Software Engineering" sẽ bị rớt.
- **Giải pháp:** Xây dựng Node `Major` (Ngành học) và tạo liên kết `RELATED_MAJOR`.
- **Truy vấn Cypher:**
  ```cypher
  MATCH (m:Major {name: $jd_major})-[:RELATED_MAJOR]-(alt:Major)
  RETURN collect(alt.name) AS equivalent_majors
  ```

---

## 4. Luồng Xử Lý Python Tổng Hợp (Execution Flow)

Luồng xử lý Query Expansion sẽ nằm ở **Layer 4 & 5**.

```python
# Ví dụ cấu trúc hàm build_enriched_query trong module query_expander.py
def build_enriched_query(jd_text: str) -> str:
    # 1. Gọi LLM trích xuất nhanh JSON từ JD (chạy cực nhanh, không gọi Graph Extractor ở đây)
    jd_json = fast_llm_extractor(jd_text) # Trả về: position, industry, skills, major, level...
    
    # 2. Query FalkorDB cho 5 chiều không gian
    titles = get_equivalent_titles(jd_json['position'])
    companies = get_competitors(jd_json['industry'])
    certs = get_related_certificates(jd_json['skills'])
    alt_skills = get_alternative_skills(jd_json['skills'])
    majors = get_related_majors(jd_json['major'])
    
    # Mở rộng bằng Python Code (Không dùng Graph)
    # Ví dụ: Mở rộng Seniority Level bằng dictionary mapping
    levels = get_higher_levels_via_python(jd_json['level'])
    
    # 3. Gom nhóm và Tăng trọng số (Lặp lại từ khóa gốc để ép điểm BM25)
    original_core = f"{jd_json['position']} {jd_json['position']} {' '.join(jd_json['skills'])}"
    expansion = f"{' '.join(titles)} {' '.join(companies)} {' '.join(certs)} {' '.join(alt_skills)} {' '.join(majors)} {' '.join(levels)}"
    
    # 4. Trả về câu truy vấn siêu cấp để đẩy vào Qdrant
    return f"{original_core} {expansion}"
```

---

## 5. Tiến Độ Triển Khai (Status)

✅ **Bước 1 (Hoàn thành):** Cập nhật `graph_schemas.py` và Mô hình Biểu diễn kép (Dual-Representation). Tách riêng Node `JobPosition`, `Major` để phục vụ xây dựng Ontology.
✅ **Bước 2 (Hoàn thành):** Xây dựng `ontology_wire.py` với chiến lược **Incremental Wiring** (chỉ xử lý Orphan Nodes) và **Triple-Trigger Architecture** (Background Task, APScheduler Cronjob, Just-In-Time) để tự động nối dây Đồ thị mà không sợ tốn LLM Tokens hay quá tải.
✅ **Bước 3 (Hoàn thành):** Xây dựng module `query_expansion.py` (hoặc `query_expander.py`). Viết code Python thực thi các luồng Cypher của 5 Chiều không gian để sinh ra `enriched_query`.
✅ **Bước 4 (Hoàn thành):** Đấu nối `enriched_query` vào tầng Search của `Qdrant` (cho cả Sparse và Dense vector) tại Layer 5. Mở rộng Reranker với `GraphScorer` dùng `Anchor ID`.
