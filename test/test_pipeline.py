from GRAPHRAG.graph_schemas import (
    GraphExtractionSchema, ExtractedNode, ExtractedEdge,
    WorkedAtProperties, EarnedProperties, RequiresSkillProperties
)
from GRAPHRAG.entity_resolver import EntityResolver
from GRAPHRAG.falkordb_graph import FalkorDBGraph

print("=== TEST 1: Schema Optional Fields ===")
try:
    # WorkedAtProperties without required fields (should NOT crash now)
    props = WorkedAtProperties()
    print(f"✅ WorkedAtProperties() ok: position={props.position}, duration_months={props.duration_months}")
except Exception as e:
    print(f"❌ FAIL: {e}")

print("\n=== TEST 2: EntityResolver - All Node Types ===")
resolver = EntityResolver(fuzzy_cutoff=0.8)
test_nodes = [
    ExtractedNode(id_node="skill_fast-api", name="Fast-api", labels=["Skill"]),
    ExtractedNode(id_node="ind_fintech", name="fintech", labels=["Industry"]),
    ExtractedNode(id_node="group_cloud", name="cloud", labels=["SkillGroup"]),
    ExtractedNode(id_node="cert_ielts", name="IELTS", labels=["Certificate"]),
]
for node in test_nodes:
    new_name, new_id = resolver.resolve_node(node)
    print(f"  [{node.labels[0]}] '{node.name}' → '{new_name}' (id: {new_id})")

print("\n=== TEST 3: FalkorDB - Save and Read Back ===")
try:
    db = FalkorDBGraph()

    mock_graph = GraphExtractionSchema(
        nodes=[
            ExtractedNode(id_node="cand_kiet", name="Kiet", labels=["Candidate"],
                          email="kiet@test.com", summary="Backend developer"),
            ExtractedNode(id_node="skill_fastapi", name="FastAPI", labels=["Skill"]),
            ExtractedNode(id_node="cert_ielts", name="IELTS", labels=["Certificate"]),
        ],
        edges=[
            ExtractedEdge(source="cand_kiet", target="skill_fastapi", edge_type="USES_SKILL"),
            ExtractedEdge(
                source="cand_kiet", target="cert_ielts", edge_type="EARNED",
                earned_props=EarnedProperties(score=7.5)
            ),
        ]
    )

    db.save_extracted_graph(mock_graph)
    print("✅ save_extracted_graph() passed.")

    entities = db.get_all_entities()
    print(f"✅ get_all_entities() returned: {entities}")

    # Cleanup
    db.delete_db()
    print("✅ Database cleaned up.")

except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()

print("\n=== TEST 4: model_dump None filtering ===")
props_with_none = EarnedProperties(score=None)
filtered = {k: v for k, v in props_with_none.model_dump().items() if v is not None}
print(f"✅ EarnedProperties(score=None) filtered dict: {filtered}  (should be empty {{}})")
