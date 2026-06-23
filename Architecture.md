# Kiến trúc Hệ thống AI CV Matcher

> Tài liệu tổng hợp kiến trúc 6-layer cho hệ thống AI chấm điểm độ phù hợp CV ↔ JD, hỗ trợ song song 2 phương án: **RAG** và **GraphRAG**.

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Layer 1 — Input Layer](#layer-1--input-layer)
3. [Layer 2 — Parsing & OCR](#layer-2--parsing--ocr)
4. [Layer 3 — Structuring (RAG / GraphRAG)](#layer-3--structuring)
5. [Layer 4 — Embedding & Indexing](#layer-4--embedding--indexing)
6. [Layer 5 — Multi-Dimensional Matching](#layer-5--multi-dimensional-matching)
7. [Layer 6 — LLM Evaluation & Scoring](#layer-6--llm-evaluation--scoring)
8. [So sánh RAG vs GraphRAG](#8-so-sánh-rag-vs-graphrag)
9. [Các vấn đề thiết kế quan trọng](#9-các-vấn-đề-thiết-kế-quan-trọng)
10. [Bảng tổng hợp công nghệ](#10-bảng-tổng-hợp-công-nghệ)
11. [Khuyến nghị triển khai theo giai đoạn](#11-khuyến-nghị-triển-khai-theo-giai-đoạn)

---

## 1. Tổng quan kiến trúc

```
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1 — INPUT                                                    │
│ CV (PDF/DOCX/Image) + JD (Form/Text/Image/PDF) + Scoring Config    │
└──────────────────────────────┬────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2 — PARSING & OCR                                            │
│ Native PDF / DOCX / Scan-Image → Raw Text (giữ layout)              │
└──────────────────────────────┬────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3 — STRUCTURING                                              │
│   ├─ RAG:       LLM Extractor → JSON Schema                        │
│   └─ GraphRAG:  LLM Extractor → Entities + Relationships           │
└──────────────────────────────┬────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 4 — EMBEDDING & INDEXING                                     │
│   ├─ RAG:       Vector Embedding → Vector DB                       │
│   └─ GraphRAG:  Graph Construction → Graph DB (+ vector index)     │
└──────────────────────────────┬────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 5 — MULTI-DIMENSIONAL MATCHING                                │
│   Hard-match (rule cứng, code thuần)                                │
│   ├─ RAG:       Hybrid Search (BM25 + Cosine) → Top-K → Re-rank    │
│   └─ GraphRAG:  Graph Traversal (Cypher/Gremlin) → Re-rank          │
└──────────────────────────────┬────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 6 — LLM EVALUATION & SCORING                                  │
│ Output: { match_score, breakdown, missing_skills, strengths,       │
│           reasoning }                                                │
└──────────────────────────────┬────────────────────────────────────┘
                                ▼
                    Ranked List CV phù hợp
```

---

## Layer 1 — Input Layer

| Thành phần | Định dạng hỗ trợ | Nguồn |
|---|---|---|
| CV | PDF (native/scan), DOCX, Image (JPG/PNG) | Ứng viên upload |
| JD | Form nhập tay, Text thuần, Image, PDF | HR / hệ thống tuyển dụng |
| Scoring Config | JSON config (trọng số rubric) | HR (có giới hạn, xem mục 9.3) |

---

## Layer 2 — Parsing & OCR

### Routing logic theo loại file

```
File Input
   │
   ├─ Native PDF (có text layer)? ──Yes──► pdfplumber / pymupdf
   │
   ├─ DOCX? ──Yes──► python-docx
   │
   └─ Scan / Image
        │
        ├─ Layout đơn giản (1 cột, ít graphic) ──► Surya OCR
        │
        └─ Layout phức tạp (đa cột, bảng, timeline graphic)
                  ──► VLM (Qwen3-VL / Gemini qua OpenRouter)
                       hoặc MinerU (fallback)
```

### Công nghệ chi tiết

| Công cụ | Vai trò | Ưu điểm | Nhược điểm |
|---|---|---|---|
| `pdfplumber` | Extract text từ PDF native | Nhanh, chính xác 100%, free | Không xử lý được scan/ảnh |
| `pymupdf` (fitz) | Extract text + layout PDF native | Nhanh hơn pdfplumber, hỗ trợ rendering | Cần xử lý thêm cho bảng phức tạp |
| `python-docx` | Extract text/structure từ DOCX | Native support structure (heading, bullet) | Chỉ dùng cho .docx, không dùng cho .doc cũ |
| **Surya OCR** | OCR + layout detection cho ảnh/scan | Detect bounding box, hỗ trợ đa cột, nhanh trên GPU | Cần GPU để tối ưu tốc độ |
| **MinerU** | OCR + layout phức tạp (fallback) | Xử lý tốt PDF có layout phức tạp, bảng | Chậm hơn Surya |
| **Qwen3-VL** (VLM) | Đọc hiểu layout bằng vision-language model | Hiểu bố cục như người, xử lý tốt CV thiết kế phức tạp (Canva, đa cột, icon) | Chi phí cao hơn, latency cao hơn OCR truyền thống |

### Thử thách quan trọng: CV đa cột (multi-column layout)

> Nếu đọc text theo thứ tự trái→phải thông thường, nội dung 2 cột sẽ bị **trộn lẫn**, mất hoàn toàn ngữ cảnh.

**Giải pháp:** Dùng Surya/MinerU để detect **bounding box theo block** trước, sau đó build lại reading order theo từng block riêng biệt (top-to-bottom trong mỗi cột, rồi mới sang cột kế tiếp) — không đọc raw text tuần tự theo toạ độ x.

---

## Layer 3 — Structuring

### Nhánh RAG: LLM Extractor → JSON Schema

**Model:** LLM có structured output tốt (Claude, GPT, qua function calling / JSON mode)

```python
class WorkExperience(BaseModel):
    company: str
    position: str
    start_date: date
    end_date: date | None  # None = đang làm
    skills_used: list[str]
    seniority_level: str  # "Junior" / "Mid" / "Senior"

class CVSchema(BaseModel):
    personal_info: dict
    name: str
    skills: list[str]
    experience: list[WorkExperience]
    companies: list[str]
    education: str
    certs: list[str]
    industry: str
    domain_specific_fields: dict  # field linh hoạt theo ngành

class JDSchema(BaseModel):
    position: str
    required_skills: list[str]
    nice_to_have: list[str]
    min_exp_years: float
    level: str
    domain: str
    industry: str
```

### Nhánh GraphRAG: Entities + Relationships

**Nodes (Entities):**
- `Candidate`, `Company`, `Skill`, `JobTitle`, `Degree`, `Domain`

**Edges (Relationships):**
```
(Candidate) -[WORKED_AT]-> (Company)
(Candidate) -[HAS_SKILL]-> (Skill)
(Skill) -[PART_OF]-> (Domain)              // VD: React → Frontend
(Candidate) -[HOLDS_DEGREE]-> (Degree)
(JobTitle) -[REQUIRES]-> (Skill)
(Skill) -[RELATED_TO]-> (Skill)            // VD: React ~ Next.js
(Company) -[OPERATES_IN]-> (Domain)        // VD: Company X → Fintech
```

---

## Layer 4 — Embedding & Indexing

### Nhánh RAG

| Thành phần | Công nghệ | Lý do chọn |
|---|---|---|
| Embedding model | **`bge-m3`** | Multilingual, hỗ trợ tốt tiếng Việt — phù hợp hơn `text-embedding-3-small` (tối ưu chủ yếu cho tiếng Anh) |
| Vector DB | **Qdrant** | Hỗ trợ hybrid search (dense + sparse) native, payload filter mạnh |
| Metadata Store | **PostgreSQL** | Lưu structured fields để hard-filter (exp_years, domain, location...) |
| Sparse Index | BM25 (qua Qdrant hoặc Elasticsearch) | Bắt exact-match cho tên công nghệ, tên trường, từ viết tắt |

### Nhánh GraphRAG

| Thành phần | Công nghệ | Lý do chọn |
|---|---|---|
| Graph DB | **Neo4j** hoặc **FalkorDB** | Neo4j: ecosystem lớn, Cypher mature. FalkorDB: nhanh hơn cho graph lớn, tương thích Redis |
| Vector index trên node | Neo4j native vector index | Cho phép hybrid graph + vector trong cùng 1 query |
| Skill Ontology | Build tay hoặc LLM-generate + human review | Cần chuẩn hóa quan hệ `PART_OF`, `RELATED_TO` giữa skill |

> ⚠️ **Lưu ý:** `text-embedding-3-small` nên tránh dùng cho hệ thống xử lý tiếng Việt là chính — ưu tiên `bge-m3` hoặc các model multilingual tương đương.

---

## Layer 5 — Multi-Dimensional Matching

### Hard-match — PHẢI là code logic thuần, KHÔNG giao cho LLM

> ❌ Sai: dùng System Prompt để LLM "tự áp rule" — không deterministic, khó audit, dễ sai khi tính toán (VD: cộng tháng kinh nghiệm).
>
> ✅ Đúng: rule cứng viết bằng code (Python/Pydantic), chạy trên structured data từ Layer 3.

```python
def hard_match(cv: CVSchema, jd: JDSchema) -> dict:
    relevant_months = sum(
        months_between(exp.start_date, exp.end_date)
        for exp in cv.experience
        if domain_match(exp.skills_used, jd.domain)
    )
    return {
        "exp_passed": relevant_months >= jd.min_exp_years * 12,
        "required_certs_passed": set(jd.required_skills).issubset(set(cv.skills)),
        "relevant_months": relevant_months,
    }
```

### Soft-match — Nhánh RAG: Hybrid Retrieval

```
Pre-filter (metadata: industry, domain, location)
        │
        ▼
Hybrid Search = BM25 (sparse) + Cosine Similarity (dense)
        │  (kết hợp bằng RRF — Reciprocal Rank Fusion)
        ▼
Top-K (lọc theo số lượng tuyệt đối, VD: 50 candidates)
        │
        ▼
Re-rank bằng Cross-Encoder → Top-N (lọc theo thứ hạng/chất lượng)
```

### Soft-match — Nhánh GraphRAG: Graph Traversal

```cypher
MATCH (c:Candidate)-[:HAS_SKILL]->(s:Skill)
      -[:RELATED_TO*0..2]->(req:Skill)
      <-[:REQUIRES]-(jd:JobTitle {id: $jd_id})
RETURN c, count(DISTINCT req) AS matched_skills
```

→ Tìm được candidate có skill **"gần" yêu cầu qua 1–2 hop quan hệ** (VD: JD cần "Cloud Architecture", CV có "AWS"/"GCP" → graph biết cả hai đều `PART_OF` Cloud Architecture).

**Ví dụ multi-hop reasoning:**
```
Candidate → WORKED_AT → Company A → OPERATES_IN → Fintech
                                          ▲
Candidate → WORKED_AT → Company B → OPERATES_IN → Fintech
```
→ Suy luận "ứng viên có kinh nghiệm domain tương đương" dù tên công ty khác nhau hoàn toàn.

> ⚠️ Sau graph traversal, vẫn cần thêm bước **re-rank** (cross-encoder hoặc weighted edge score) trước khi sang Layer 6 — không nên chỉ dựa vào số lượng `matched_skills` thô.

---

## Layer 6 — LLM Evaluation & Scoring

### Input vào LLM Scorer
- JD structured + CV structured (từ Layer 3)
- Kết quả Hard-match (pass/fail từng điều kiện)
- Kết quả Soft-match (similarity score hoặc subgraph summary)
- Scoring Config (trọng số rubric, có guardrail — xem mục 9.3)

### Nhánh RAG — Input dạng text trực tiếp
```
"Ứng viên có kinh nghiệm Backend tại Công ty A (Junior, 2020-2022) và
Công ty B (Senior, 2022-2024), tổng 4 năm liên quan Backend. JD yêu cầu
Senior Backend, tối thiểu 3 năm. Career progression Junior→Senior là
tín hiệu tích cực."
```

### Nhánh GraphRAG — Input dạng subgraph summary (đã tóm tắt)
```
"Candidate X có 3 skill liên quan Backend (Python, Django, FastAPI)
kết nối với domain Fintech (từng làm ở 2 công ty cùng domain), thiếu
trực tiếp Kubernetes nhưng có Docker (RELATED_TO Kubernetes, độ liên
quan 0.7)."
```

### Output JSON chuẩn (áp dụng cho cả 2 nhánh)
```json
{
  "match_score": 78,
  "breakdown": {
    "skills": 85,
    "experience": 70,
    "education": 90,
    "culture_fit": 65
  },
  "missing_skills": ["Kubernetes", "GraphQL"],
  "strengths": [
    "Career progression rõ ràng Junior → Senior",
    "Kinh nghiệm cùng domain Fintech"
  ],
  "reasoning": "Ứng viên đáp ứng tốt yêu cầu kỹ thuật cốt lõi, có lộ trình thăng tiến rõ ràng, nhưng thiếu kinh nghiệm trực tiếp với Kubernetes."
}
```

> Đối với GraphRAG: `missing_skills` được suy ra từ các edge `REQUIRES` của JobTitle không có path kết nối tới Candidate trong subgraph.

---

## 8. So sánh RAG vs GraphRAG

| Tiêu chí | RAG | GraphRAG |
|---|---|---|
| Đơn vị lưu trữ | Vector (CV/JD chunk) | Node + Edge (entity + relationship) |
| Cách "hiểu" ngữ cảnh | Embedding similarity | Graph traversal (multi-hop) |
| Độ phức tạp xây dựng | Thấp–trung bình | **Cao** (cần build Skill Ontology, entity resolution) |
| Chi phí hạ tầng | Vector DB (Qdrant) | Vector DB + Graph DB (Neo4j/FalkorDB) — 2 hệ thống |
| Latency | Thấp | Cao hơn (graph traversal nhiều hop) |
| Khả năng multi-hop reasoning | Hạn chế (phụ thuộc embedding) | **Mạnh** (transitive relationship rõ ràng, giải trình được từng bước) |
| Khả năng maintain khi data tăng | Dễ | Khó hơn (graph dễ "rối" nếu không chuẩn hóa entity) |
| Phù hợp nhất khi | Bài toán point-to-point matching (CV ↔ JD trực tiếp) | Cần suy luận quan hệ gián tiếp nhiều lớp (domain tương đương, skill taxonomy) |

**Khuyến nghị:** Với CV matching, bản chất là **point-to-point matching**, không có quan hệ nhiều hop phức tạp như domain y tế (thuốc–bệnh lý–chống chỉ định). RAG (hybrid) thường **đủ và hiệu quả hơn về chi phí/lợi ích**. GraphRAG chỉ nên xét đến khi cần mở rộng: skill ontology, career path reasoning, hoặc company-domain network.

**Phương án lai (khuyến nghị thực tế):** Dùng Vector DB cho retrieval chính + Graph DB **nhỏ** chỉ chứa Skill Ontology (`Skill -[RELATED_TO]-> Skill`, `Skill -[PART_OF]-> Domain`) để mở rộng query trước khi vector search — tận dụng điểm mạnh multi-hop cho phần dữ liệu ổn định (skill taxonomy), không phải graph hóa toàn bộ CV (dữ liệu thay đổi liên tục).

---

## 9. Các vấn đề thiết kế quan trọng

### 9.1. Đa ngành (multi-industry)

- Không cần nhiều hệ thống riêng theo ngành — dùng **1 pipeline chung**, khác nhau ở: schema extraction (field chung + field linh hoạt theo ngành), scoring rubric, và **metadata filter cứng theo industry** trước khi vector search.
- Luôn kết hợp filter `industry`/`domain` — không để vector similarity tự quyết định 100%, vì văn bản khác ngành có thể vô tình "gần" nhau về wording.

### 9.2. Tính kinh nghiệm khi có nhiều vị trí/công ty khác nhau

| Tình huống | Cách xử lý |
|---|---|
| 2 công ty, chức danh khác, **cùng domain**, liên tục | Cộng dồn (rule-based theo `skills_used` + date range, không dựa vào text `position`) |
| 2 công ty, cùng domain, có thăng cấp (Junior→Senior) | Cộng dồn + LLM ghi nhận là **điểm cộng** (career growth signal) |
| 2 công ty, **domain khác hẳn** | KHÔNG cộng dồn vào kinh nghiệm domain mục tiêu |
| 2 công ty, domain gần nhau (overlap) | Cộng dồn một phần, cần đánh giá % liên quan (embedding/skill taxonomy) |

> Nguyên tắc cốt lõi: **không để LLM/vector tự "đoán" việc cộng dồn kinh nghiệm** — đây phải là phép tính rõ ràng dựa trên dữ liệu structured (`skills_used`, `start_date`, `end_date`).

### 9.3. Scoring Config — set cứng hay để HR tự chỉnh?

**Khuyến nghị: Hybrid — Default thông minh + Override có giới hạn (guardrail)**

```python
class ScoringWeights(BaseModel):
    skills: float = Field(ge=0.2, le=0.6)
    experience: float = Field(ge=0.1, le=0.5)
    education: float = Field(ge=0.0, le=0.3)
    culture_fit: float = Field(ge=0.0, le=0.3)

    @model_validator(mode="after")
    def check_sum(self):
        total = self.skills + self.experience + self.education + self.culture_fit
        if not (0.95 <= total <= 1.05):
            raise ValueError("Tổng trọng số phải ≈ 100%")
        return self
```

- Không cho nhập số tự do — dùng **slider có range giới hạn** hoặc **preset template theo job family** (Technical / Management / Sales...).
- Lý do: tránh HR vô tình tạo bias (VD: đặt trọng số Education quá cao loại bỏ ứng viên tự học giỏi), và giữ khả năng audit/giải trình khi cần (một số khu vực pháp lý coi hệ thống AI tuyển dụng là "high-risk", VD EU AI Act).

### 9.4. Routing OCR theo đặc điểm CV thực tế

```
CV Input
   │
   ├─ Native PDF? ──Yes──► pdfplumber (nhanh, free, chính xác nhất)
   │
   └─ No (scan/ảnh)
        │
        ├─ Layout đơn giản ──► Surya OCR
        │
        └─ Layout phức tạp (đa cột/graphic) ──► VLM (Qwen3-VL/Gemini)
```

---

## 10. Bảng tổng hợp công nghệ

| Layer | Thành phần | Công nghệ đề xuất |
|---|---|---|
| 2 — Parsing | PDF native | pdfplumber, pymupdf |
| 2 — Parsing | DOCX | python-docx |
| 2 — OCR | Scan/Image cơ bản | Surya OCR |
| 2 — OCR | Layout phức tạp | MinerU, Qwen3-VL (VLM) |
| 3 — Extraction | LLM Extractor | Claude / GPT (structured output, Pydantic schema) |
| 4 — Embedding (RAG) | Embedding model | **bge-m3** (multilingual, ưu tiên cho tiếng Việt) |
| 4 — Vector DB (RAG) | Lưu trữ vector | Qdrant |
| 4 — Metadata (RAG) | Lưu trữ structured field | PostgreSQL |
| 4 — Graph DB (GraphRAG) | Lưu trữ entity/relationship | Neo4j, FalkorDB |
| 5 — Hard-match | Rule logic | Python/Pydantic (code thuần, KHÔNG qua LLM) |
| 5 — Soft-match (RAG) | Hybrid search | BM25 + Cosine Similarity (RRF fusion) |
| 5 — Soft-match (RAG) | Re-rank | Cross-encoder |
| 5 — Soft-match (GraphRAG) | Graph query | Cypher (Neo4j) / Gremlin |
| 6 — Scoring | LLM Scorer | Claude / GPT (structured output JSON) |

---

## 11. Khuyến nghị triển khai theo giai đoạn

| Giai đoạn | Approach |
|---|---|
| **MVP / POC** | RAG đơn giản + structured extraction; Scoring set cứng theo 2–3 template (Technical/Non-technical/Management) |
| **Production** | Hybrid RAG (dense + sparse) + metadata filter theo industry; HR override scoring có giới hạn (slider, không nhập số tự do) |
| **Advanced** | Thêm Skill Ontology Graph (GraphRAG một phần — chỉ graph hóa skill taxonomy, không graph hóa toàn bộ CV) để tăng recall cho semantic search |

---

*Tài liệu này tổng hợp từ quá trình thiết kế kiến trúc AI CV Matcher, áp dụng cho hệ thống xử lý CV/JD tiếng Việt với pipeline OCR (Surya/MinerU/VLM) đã có sẵn.*