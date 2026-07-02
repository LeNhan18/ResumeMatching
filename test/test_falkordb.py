from GRAPHRAG.falkordb_graph import FalkorDBGraph

try:
    db = FalkorDBGraph()
    entities = db.get_all_entities()
    print("SUCCESS: Connected to FalkorDB!")
    print(f"Entities found: {entities}")
except Exception as e:
    print(f"Connection failed (is FalkorDB running?): {e}")
