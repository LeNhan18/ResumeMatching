# FalkorDB Graph (`falkordb_graph.py`)

## Mục tiêu
`falkordb_graph.py` chịu trách nhiệm kết nối, truy vấn và quản trị cơ sở dữ liệu đồ thị FalkorDB (phiên bản Graph chạy in-memory trên nền Redis cực kỳ mạnh mẽ).

## Tính năng chính
- **Khởi tạo và Xóa DB:** Chức năng kết nối và làm sạch môi trường test thông qua `FalkorDB` driver.
- **Lưu trữ Cấu trúc (Save Extracted Graph):** 
  - Biến các object `ExtractedNode` và `ExtractedEdge` thành câu lệnh Cypher (`MERGE` và `SET`) để đưa vào Graph.
  - Sử dụng cơ chế `exclude_none=True` để loại bỏ các trường bị trống nhằm tương thích với FalkorDB.
  - Phân luồng xử lý thông minh giữa việc Cạnh (Edge) có thuộc tính và không có thuộc tính để xây dựng query phù hợp.
- **Truy vấn Dữ liệu Động (Get All Entities):** Cung cấp API `get_all_entities()` quét toàn bộ dữ liệu trong Database, trả về một dictionary nhóm theo loại Entity (Skill, Company, Industry...) để cho `EntityResolver` có cái nhìn "thực tế" về các chuẩn mực hiện tại trong DB.

## Lợi ích kiến trúc
Tách bạch hoàn toàn phần Database Layer khỏi Logic xử lý, giúp dễ dàng mở rộng sang các CSDL khác (Neo4j, Memgraph) sau này.
