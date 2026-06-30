from GRAPHRAG.graph_schemas import GraphExtractionSchema, ExtractedNode, ExtractedEdge
from GRAPHRAG.graph_extractor import GraphExtractor

# Mock LLM Client
class MockLLM:
    pass

extractor = GraphExtractor(MockLLM())

# Simulate an LLM output with messy names and IDs
mock_schema = GraphExtractionSchema(
    nodes=[
        ExtractedNode(id_node="cand_1", name="Kiet", labels=["Candidate"]),
        ExtractedNode(id_node="skill_fast-api", name="Fast-api", labels=["Skill"]),
        ExtractedNode(id_node="school_bk_tphcm", name="bk tphcm", labels=["School"]),
        ExtractedNode(id_node="comp_fsoft", name="fsoft", labels=["Company"]),
    ],
    edges=[
        ExtractedEdge(source="cand_1", target="skill_fast-api", edge_type="USES_SKILL"),
        ExtractedEdge(source="cand_1", target="school_bk_tphcm", edge_type="STUDIED_AT"),
        ExtractedEdge(source="cand_1", target="comp_fsoft", edge_type="WORKED_AT"),
    ]
)

print("--- BEFORE POST-PROCESSING ---")
for n in mock_schema.nodes:
    print(f"Node: {n.id_node} | Name: {n.name}")
for e in mock_schema.edges:
    print(f"Edge: {e.source} -> {e.target}")

processed_schema = extractor._post_process_graph(mock_schema)

print("\n--- AFTER POST-PROCESSING ---")
for n in processed_schema.nodes:
    print(f"Node: {n.id_node} | Name: {n.name}")
for e in processed_schema.edges:
    print(f"Edge: {e.source} -> {e.target}")

