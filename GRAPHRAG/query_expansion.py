from typing import List, Set
from GRAPHRAG.falkordb_graph import FalkorDBGraph
from RAG.schemas import JDSchema
from GRAPHRAG.ontology_wire import OntologyWire
from utils.logger import setup_logger

logger = setup_logger("QueryExpander", log_file="query_expansion.log")

class QueryExpander:
    def __init__(self, graph: FalkorDBGraph = None):
        self.graph = graph.graph if graph else FalkorDBGraph().graph
        self.SENIORITY_HIERARCHY = ["Intern", "Fresher", "Junior", "Mid", "Senior", "Lead", "Principal"]

    def _expand_seniority_level(self, required_level: str) -> List[str]:
        """
        Search seniority levels based on hierarchy.
        Example: Junior -> find Junior, Senior, Mid
        """
        if not required_level:
            return []
        try:
            idx = self.SENIORITY_HIERARCHY.index(required_level.strip().title())
            return self.SENIORITY_HIERARCHY[idx:idx+2] # Only take 2 higher levels to avoid being too broad
        except ValueError:
            return [required_level] # If not found, return itself

    def _trigger_just_in_time_wiring(self):
        """Activate Just-in-Time Wiring before Query to ensure Graph is up-to-date."""
        logger.info("Executing Just-In-Time Ontology Wiring check...")
        try:
            wire = OntologyWire()
            # Threshold = 1 to handle scattered nodes just uploaded immediately
            wire.wire_major_ontology(threshold=1)
            wire.wire_jobposition_ontology(threshold=1)
            wire.wire_skill_ontology(threshold=1)
            wire.wire_skillgroup_skill_ontology(threshold=1)
            wire.wire_company_industry_ontology(threshold=1)
        except Exception as e:
            logger.error(f"Just-In-Time Wiring failed (Non-fatal): {e}")

    def build_enriched_query(self, jd: JDSchema) -> str:
        """
        Expand query for Qdrant by getting related nodes from FalkorDB Graph.
        """
        # 0. Trigger Just-in-time Wiring before Query
        self._trigger_just_in_time_wiring()

        # 1. Collect original keywords for boosting BM25 weight
        original_core = []
        if jd.position: original_core.append(jd.position)
        if jd.required_skills: original_core.extend(jd.required_skills)
        if jd.industry: original_core.append(jd.industry)
        if jd.domain: original_core.append(jd.domain)
        
        # Use List for original keywords (Allow duplicates to activate BM25)
        original_query = " ".join([str(k) for k in original_core if k])
        
        # Use Set for expansion keywords to avoid redundant repetition
        expanded_keywords: Set[str] = set()

        # 1. Expand Job Positions
        if jd.position:
            cypher_position = """
            MATCH (jp: JobPosition {name: $position})-[r:EQUIVALENT_TO]-(alt_jp:JobPosition)
            RETURN collect(DISTINCT alt_jp.name) AS positions
            """
            position_results = self.graph.query(cypher_position, params={'position': jd.position})
            if position_results.result_set and position_results.result_set[0][0]:
                expanded_keywords.update(position_results.result_set[0][0])

        # 2. Expand Companies by Industry
        if jd.industry:
            cypher_industry = """
            MATCH (i:Industry {name: $industry})<-[r:BELONGS_TO]-(c:Company)
            RETURN collect(DISTINCT c.name) AS companies
            """
            industry_results = self.graph.query(cypher_industry, params={'industry': jd.industry})
            if industry_results.result_set and industry_results.result_set[0][0]:
                expanded_keywords.update(industry_results.result_set[0][0])

        # 3. Expand Skills, Groups, and Certs
        if jd.required_skills and len(jd.required_skills) > 0:
            cypher_skills = """
            MATCH (s:Skill) WHERE s.name IN $skills
            OPTIONAL MATCH (s)-[:ALTERNATIVE_TO]-(alt_s:Skill)
            OPTIONAL MATCH (s)-[:BELONGS_TO]->(sg:SkillGroup)
            OPTIONAL MATCH (s)-[:VALIDATES_SKILL]-(cert:Certificate)
            RETURN collect(DISTINCT alt_s.name) AS alts, collect(DISTINCT sg.name) AS groups, collect(DISTINCT cert.name) AS certs
            """
            res_skills = self.graph.query(cypher_skills, params={'skills': jd.required_skills})
            if res_skills.result_set:
                expanded_keywords.update(res_skills.result_set[0][0] or [])
                expanded_keywords.update(res_skills.result_set[0][1] or [])
                expanded_keywords.update(res_skills.result_set[0][2] or [])

        # 4. Expand Majors
        if jd.major:
            cypher_major = """
            MATCH (m:Major {name: $major})-[r:RELATED_MAJOR]-(alt_m:Major)
            RETURN collect(DISTINCT alt_m.name) AS majors
            """
            res_major = self.graph.query(cypher_major, params={'major': jd.major})
            if res_major.result_set and res_major.result_set[0][0]:
                expanded_keywords.update(res_major.result_set[0][0])

        # 5. Expand Seniority Levels
        if jd.level:
            seniority_levels = self._expand_seniority_level(jd.level)
            expanded_keywords.update(seniority_levels)

        # Remove keyword trống and convert to lowercase
        clean_expansion = [str(kw).lower().strip() for kw in expanded_keywords if kw and str(kw).strip()]
        expansion_query = " ".join(clean_expansion)

        # Boosting weight: Re-type original keyword 2 times for Qdrant BM25 to find accurately
        # Formula: (Core x 2) + Expansion
        super_query = f"{original_query} {original_query} {expansion_query}".strip()
        
        logger.info(f"Original JD Core: {original_query}")
        logger.info(f"Graph Expanded: {expansion_query}")
        
        return super_query