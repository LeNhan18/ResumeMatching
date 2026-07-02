from LLM.client import LLMClient
from GRAPHRAG.graph_schemas import GraphExtractionSchema
from GRAPHRAG.prompts import EXTRACT_CV_PROMPT_SYSTEM
from GRAPHRAG.entity_resolver import EntityResolver
from GRAPHRAG.falkordb_graph import FalkorDBGraph
from utils.logger import setup_logger

logger = setup_logger("GraphExtractor", log_file="graph_extractor.log")

class GraphExtractor:
    def __init__(self, llm_client: LLMClient, db_graph: FalkorDBGraph = None):
        self.llm_client = llm_client
        self.db_graph = db_graph

    def extract_graph_from_cv(self, text: str, document_id: str, auto_save: bool = True) -> GraphExtractionSchema:
        """
        Extract a knowledge graph from a candidate's CV using an LLM.
        
        Args:
            text: The text content of the CV.
            document_id: The unique identifier for this document (e.g., candidate ID).
            auto_save: If True and db_graph is provided, automatically saves result to FalkorDB.
            
        Returns:
            A GraphExtractionSchema object containing the extracted nodes and edges.
        """
        if not text or not text.strip() or self.llm_client is None:
            logger.error("CV text cannot be empty or LLM client is missing.")
            return self.get_extraction_mock()

        doc_type = "CV (Candidate Resume)"
        system_prompt = EXTRACT_CV_PROMPT_SYSTEM
        user_prompt = f"Let's analyze the {doc_type} below:\n\n{text}"

        logger.info(f"Extracting knowledge graph from {doc_type} with ID: {document_id}")
        try:
            response = self.llm_client.generate_structured(
                prompt=user_prompt,
                response_model=GraphExtractionSchema,
                system_prompt=system_prompt,
                temperature=0.1,
            )

            if response and response.nodes:
                logger.info(f"Successfully extracted {len(response.nodes)} nodes and {len(response.edges)} edges for {document_id}")
                cleaned_response = self._post_process_graph(response, document_id=document_id)

                if auto_save and self.db_graph:
                    logger.info(f"Auto-saving graph for {document_id} to FalkorDB...")
                    self.db_graph.save_extracted_graph(cleaned_response)

                return cleaned_response
            else:
                logger.warning(f"No nodes found in LLM response for {document_id}")
                return self.get_extraction_mock()

        except Exception as e:
            logger.error(f"Failed to extract graph for {document_id}: {str(e)}")
            return self.get_extraction_mock()

    def _post_process_graph(self, schema: GraphExtractionSchema, document_id: str = None) -> GraphExtractionSchema:
        """
        Cleans and validates the extracted graph to prevent Graph Database insertion crashes.
        - Resolves Entity names (Dictionary + Fuzzy Matching).
        - Enforces deterministic, lowercase, and stripped IDs.
        - Removes dangling edges (where source or target is not in the node list).
        """
        # Load dynamic golden records from FalkorDB for real-time fuzzy matching
        dynamic_records = {}
        if self.db_graph:
            dynamic_records = self.db_graph.get_all_entities()
        
        resolver = EntityResolver(fuzzy_cutoff=0.8, dynamic_golden_records=dynamic_records)

        # 1. Normalize node IDs and Names
        valid_node_ids = set()
        id_mapping = {}

        for node in schema.nodes:
            if not node.id_node: continue
            
            old_id = str(node.id_node).strip().lower()
            
            # Resolve Node (Layer 2 & Layer 3)
            new_name, new_id = resolver.resolve_node(node, document_id=document_id)
            
            # Update Node
            node.name = new_name
            node.id_node = new_id
            
            # Track ID changes to update edges later
            if old_id != new_id:
                id_mapping[old_id] = new_id
                
            valid_node_ids.add(new_id)

        # 2. Filter invalid edges & normalize edge IDs
        valid_edges = []
        for edge in schema.edges:
            edge.source = str(edge.source).strip().lower()
            edge.target = str(edge.target).strip().lower()

            # Apply ID mapping if a node's ID was changed during resolution
            edge.source = id_mapping.get(edge.source, edge.source)
            edge.target = id_mapping.get(edge.target, edge.target)

            # Check referential integrity
            if edge.source in valid_node_ids and edge.target in valid_node_ids:
                valid_edges.append(edge)
            else:
                logger.warning(f"Edge removed during post-processing: {edge.source} -> {edge.target} ({edge.edge_type})")

        schema.edges = valid_edges
        logger.info(f"Post-processing complete. Kept {len(schema.edges)} valid edges.")
        return schema

    def get_extraction_mock(self) -> GraphExtractionSchema:
        """Get a mock extraction for testing purposes or fallback."""
        return GraphExtractionSchema(
            nodes=[],
            edges=[]
        )