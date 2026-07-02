from GRAPHRAG.graph_schemas import GraphExtractionSchema
from falkordb import FalkorDB
from utils.logger import setup_logger

logger = setup_logger("FalkorDBGraph", log_file="falkordb_graph.log")

class FalkorDBGraph:
    def __init__(self, host="localhost", port=6379, graph_name="cv_matcher"):
        """Init FalkorDB, connect to graph or create new one.
        
        Args:
            host (str): IP address of FalkorDB server.
            port (int): Port of FalkorDB server.
            graph_name (str): Name of the graph to connect to or create.
        """
        self.db = FalkorDB(host=host, port=port)
        self.graph = self.db.select_graph(graph_name)
        logger.info(f"Connected to graph '{self.graph.name}'")

    def delete_db(self):
        """
        Delete current graph. Usually used to reset database.
        """
        self.graph.delete()
        logger.info(f"Deleted graph '{self.graph.name}'")

    def save_extracted_graph(self, graph: GraphExtractionSchema):
        """
        Save entire GraphExtractionSchema to FalkorDB Graph.
        - Automatically serialize all Node properties (flexible).
        - Filter out None values before saving to Database.
        - Handle Edges with and without properties separately.

        Args:
            graph (GraphExtractionSchema): GraphExtractionSchema object containing all information to save.
        """

        # 1. Save all nodes
        for node in graph.nodes:
            # Serialize ALL fields, remove None, then remove id_node and labels (not properties)
            props = node.model_dump(exclude_none=True)
            props.pop("id_node", None)
            props.pop("labels", None)

            label = node.labels[0] if node.labels else "Entity"
            query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
            self.graph.query(query, {"id": node.id_node, "props": props})

        logger.info(f"Saved {len(graph.nodes)} nodes to FalkorDB.")

        # 2. Save all edges (Relationships)
        saved_edge_count = 0
        for edge in graph.edges:
            # Get the correct properties object according to edge_type (VD: worked_at_props, earned_props)
            edge_props_dict = {}
            prop_attr_name = f"{edge.edge_type.lower()}_props"

            if hasattr(edge, prop_attr_name):
                specific_props = getattr(edge, prop_attr_name)
                if specific_props is not None:
                    # Remove None values — FalkorDB can't accept None
                    edge_props_dict = {
                        k: v for k, v in specific_props.model_dump().items()
                        if v is not None
                    }

            try:
                if edge_props_dict:
                    # Case 1: Edge có properties → MERGE + SET
                    query = f"""
                    MATCH (src {{id: $src_id}})
                    MATCH (tgt {{id: $tgt_id}})
                    MERGE (src)-[r:{edge.edge_type}]->(tgt)
                    SET r += $edge_props
                    """
                    self.graph.query(query, {
                        "src_id": edge.source,
                        "tgt_id": edge.target,
                        "edge_props": edge_props_dict
                    })
                else:
                    # Case 2: Edge without properties (VD: USES_SKILL, ALTERNATIVE_TO)
                    query = f"""
                    MATCH (src {{id: $src_id}})
                    MATCH (tgt {{id: $tgt_id}})
                    MERGE (src)-[:{edge.edge_type}]->(tgt)
                    """
                    self.graph.query(query, {
                        "src_id": edge.source,
                        "tgt_id": edge.target,
                    })
                saved_edge_count += 1
            except Exception as e:
                logger.error(f"Failed to save edge {edge.source} -[{edge.edge_type}]-> {edge.target}: {str(e)}")

        logger.info(f"Saved {saved_edge_count}/{len(graph.edges)} edges to FalkorDB.")

    def get_all_entities(self) -> dict:
        """
        Query all Node Names in the graph for Entity Resolution.
        Returns:
            dict: Mapping from label type (e.g., 'Skill', 'School') to list of names (list of strings).
        """
        entities = {}
        try:
            query = "MATCH (n) RETURN labels(n)[0] as label, n.name as name"
            result = self.graph.query(query)

            for record in result.result_set:
                label = record[0]
                name = record[1]
                if label and name:
                    if label not in entities:
                        entities[label] = []
                    entities[label].append(name)
            logger.info(f"Loaded {sum(len(v) for v in entities.values())} entities from Graph for Resolution.")
        except Exception as e:
            logger.error(f"Failed to fetch entities from FalkorDB: {str(e)}")

        return entities