from falkordb import FalkorDB
from pydantic import BaseModel, Field
from typing import List
from LLM.client import LLMClient
from utils.logger import setup_logger

logger = setup_logger("OntologyWire", log_file="ontology_wire.log")

class ProposeEdge(BaseModel):
    source_node_id: str = Field(..., description="ID of source node.")
    target_node_id: str = Field(..., description="ID of target node.")
    weight: float = Field(0.0, description="weight of relationship (0-1).")

class OntologyWiringSchema(BaseModel):
    proposed_edges: List[ProposeEdge] = Field(default_factory=list, description="List of relationships proposed by LLM.")

class ClusterItem(BaseModel):
    source_id: str = Field(description="ID of the unwired entity")
    group_name: str = Field(description="Name of the clustered group (e.g., Database, Frontend, IT, Healthcare)")

class AutoClusterSchema(BaseModel):
    clusters: List[ClusterItem] = Field(description="List of entities and their assigned groups")

class OntologyWire:
    def __init__(self, graph_host: str = "localhost", graph_port: int = 6379, graph_name: str = "cv_matcher"):
        self.db = FalkorDB(host=graph_host, port=graph_port)
        self.graph = self.db.select_graph(graph_name)
        self.llm = LLMClient()

    def wire_major_ontology(self, low_similarity: float = 0.6, threshold: int = 1):
        """Create relationship between Major nodes with RELATED_MAJOR Edge Type (Incremental)."""
        query_all = "MATCH (n: Major) RETURN n.id_node, n.name"
        query_unwired = "MATCH (n: Major) WHERE NOT (n)-[:RELATED_MAJOR]-() RETURN n.id_node, n.name"
        
        existing_majors = [{"id": node[0], "major": node[1]} for node in self.graph.query(query_all).result_set]
        unwired_majors = [{"id": node[0], "major": node[1]} for node in self.graph.query(query_unwired).result_set]
        
        logger.info(f"Found {len(existing_majors)} total Major nodes, {len(unwired_majors)} unwired.")

        if len(unwired_majors) < threshold or len(existing_majors) < 2:
            logger.info(f"Not enough unwired Major nodes (Threshold: {threshold}) or total nodes. Skipping.")
            return

        system_prompt = "You are a domain expert in curriculum design. Analyze the unwired Major nodes and find their relations to existing Major nodes."
        user_prompt = f"""
        All Existing Majors in Database: {existing_majors}
        Unwired Majors (Needs Processing): {unwired_majors}

        Your task is to discover and propose 'RELATED_MAJOR' edges (from specific to broad).

        CRITICAL RULES:
        1. At least ONE node in each proposed edge MUST come from the 'Unwired Majors' list.
        2. You MUST use the exact 'id' field for both 'source_node_id' and 'target_node_id'. Do NOT use names.
        3. Assign a continuous similarity weight (a float between 0.0 and 1.0) based on this strict rubric:
           - 1.0: Perfect synonyms or identical majors in different languages (e.g., 'Computer Science' and 'Khoa học máy tính').
           - 0.8 - 0.9: Highly related majors where one is a direct sub-field of the other (e.g., 'Software Engineering' and 'Computer Science').
           - 0.6 - 0.7: Moderately related majors in the same overarching field (e.g., 'Information Systems' and 'Computer Science').
           - 0.1 - 0.5: Weakly related majors that share some fundamental courses (e.g., 'Mathematics' and 'Computer Science').
           - 0.0: Completely unrelated majors.

        NOTE: Output must strictly adhere to OntologyWiringSchema. Feel free to propose edges with weights below 0.6 if a weak/medium relationship exists; our system's code will handle the filtering deterministically.
        """
        try:
            discover_ontology = self.llm.generate_structured(
                system_prompt=system_prompt, prompt=user_prompt,
                response_model=OntologyWiringSchema, temperature=0.1
            )
            for edge in discover_ontology.proposed_edges:
                if edge.weight < low_similarity: continue
                cypher = """
                    MATCH (src:Major) WHERE src.id_node = $src_id OR src.name = $src_id
                    MATCH (tgt:Major) WHERE tgt.id_node = $tgt_id OR tgt.name = $tgt_id
                    MERGE (src)-[r:RELATED_MAJOR]->(tgt)
                    SET r.similarity = $weight
                """
                self.graph.query(cypher, {"src_id": edge.source_node_id, "tgt_id": edge.target_node_id, "weight": edge.weight})
                logger.info(f"[AUTO-WIRING] {edge.source_node_id} ➔ RELATED_MAJOR ➔ {edge.target_node_id}")
        except Exception as e:
            logger.error(f"Error wiring Major ontology: {e}")

    def wire_jobposition_ontology(self, low_similarity: float = 0.6, threshold: int = 1):
        """Create relationship between JobPosition nodes with EQUIVALENT_TO Edge Type (Incremental)."""
        query_all = "MATCH (n: JobPosition) RETURN n.id_node, n.name"
        query_unwired = "MATCH (n: JobPosition) WHERE NOT (n)-[:EQUIVALENT_TO]-() RETURN n.id_node, n.name"
        
        existing_jobs = [{"id": node[0], "job": node[1]} for node in self.graph.query(query_all).result_set]
        unwired_jobs = [{"id": node[0], "job": node[1]} for node in self.graph.query(query_unwired).result_set]
        
        logger.info(f"Found {len(existing_jobs)} total JobPosition nodes, {len(unwired_jobs)} unwired.")

        if len(unwired_jobs) < threshold or len(existing_jobs) < 2: 
            logger.info(f"Not enough unwired JobPosition nodes (Threshold: {threshold}) or total nodes. Skipping.")
            return

        system_prompt = "You are an HR expert. Find semantic equivalences for the unwired JobPositions."
        user_prompt = f"""
        All Existing JobPositions in Database: {existing_jobs}
        Unwired JobPositions (Needs Processing): {unwired_jobs}

        Your task is to discover and propose 'EQUIVALENT_TO' edges between JobPositions.

        CRITICAL RULES:
        1. At least ONE node in each proposed edge MUST come from the 'Unwired JobPositions' list.
        2. You MUST use the exact 'id' field for both 'source_node_id' and 'target_node_id'. Do NOT use names.
        3. Assign a continuous similarity weight (a float between 0.0 and 1.0) based on this strict rubric:
           - 1.0: Perfect synonyms or alternate abbreviations (e.g., 'QA' and 'Quality Assurance', 'Data Eng' and 'Data Engineer').
           - 0.8 - 0.9: Highly equivalent roles with identical core tech stacks and responsibilities (e.g., 'Python Developer' and 'Backend Engineer').
           - 0.6 - 0.7: Moderately equivalent or overlapping roles with highly transferable skills (e.g., 'Fullstack Engineer' and 'Backend Engineer').
           - 0.1 - 0.5: Weakly related roles with minimal skill cross-over (e.g., 'Backend Engineer' and 'Data Scientist').
           - 0.0: Completely unrelated occupations.

        NOTE: Feel free to propose edges with weights below 0.6 if a weak/medium relationship exists; our system's code will handle the filtering deterministically.
        """
        try:
            discover_ontology = self.llm.generate_structured(
                system_prompt=system_prompt, prompt=user_prompt,
                response_model=OntologyWiringSchema, temperature=0.1
            )
            for edge in discover_ontology.proposed_edges:
                if edge.weight < low_similarity: continue
                cypher = """
                    MATCH (src:JobPosition) WHERE src.id_node = $src_id OR src.name = $src_id
                    MATCH (tgt:JobPosition) WHERE tgt.id_node = $tgt_id OR tgt.name = $tgt_id
                    MERGE (src)-[r:EQUIVALENT_TO]->(tgt)
                    SET r.similarity = $weight
                """
                self.graph.query(cypher, {"src_id": edge.source_node_id, "tgt_id": edge.target_node_id, "weight": edge.weight})
                logger.info(f"[AUTO-WIRING] {edge.source_node_id} ➔ EQUIVALENT_TO ➔ {edge.target_node_id}")
        except Exception as e:
            logger.error(f"Error wiring JobPosition ontology: {e}")

    def wire_skill_ontology(self, low_similarity: float = 0.5, threshold: int = 1):
        """Create relationship between Skill nodes with ALTERNATIVE_TO (Incremental)."""
        query_all = "MATCH (n: Skill) RETURN n.id_node, n.name"
        query_unwired = "MATCH (n: Skill) WHERE NOT (n)-[:ALTERNATIVE_TO]-() RETURN n.id_node, n.name"
        
        existing_skills = [{"id": node[0], "skill": node[1]} for node in self.graph.query(query_all).result_set]
        unwired_skills = [{"id": node[0], "skill": node[1]} for node in self.graph.query(query_unwired).result_set]
        
        logger.info(f"Found {len(existing_skills)} total Skill nodes, {len(unwired_skills)} unwired.")

        if len(unwired_skills) < threshold or len(existing_skills) < 2:    
            logger.info(f"Not enough unwired Skill nodes (Threshold: {threshold}) or total nodes. Skipping.")
            return

        system_prompt = "You are an IT expert. Find alternative/substitutable technologies for the unwired Skills."
        user_prompt = f"""
        All Existing Skills in Database: {existing_skills}
        Unwired Skills (Needs Processing): {unwired_skills}

        Your task is to discover and propose 'ALTERNATIVE_TO' edges between Skills (e.g., AWS vs GCP).

        CRITICAL RULES:
        1. At least ONE node in each proposed edge MUST come from the 'Unwired Skills' list.
        2. You MUST use the exact 'id' field for both 'source_node_id' and 'target_node_id'. Do NOT use names.
        3. Assign a continuous similarity weight (a float between 0.0 and 1.0) based on this strict rubric:
           - 1.0: Perfect synonyms or alternate names for the same technology (e.g., 'React' and 'ReactJS', 'Node' and 'Node.js').
           - 0.8 - 0.9: Direct competitors or highly substitutable technologies in the same domain (e.g., 'AWS' and 'GCP', 'MySQL' and 'PostgreSQL', 'React' and 'Vue').
           - 0.6 - 0.7: Technologies that serve similar broad purposes but have different use cases (e.g., 'MongoDB' and 'PostgreSQL').
           - 0.1 - 0.5: Weakly related technologies that might be part of the same stack but are not substitutable (e.g., 'React' and 'Node.js').
           - 0.0: Completely unrelated technologies.

        NOTE: Feel free to propose edges with weights below 0.5 if a weak relationship exists; our system's code will handle the filtering deterministically.
        """
        try:
            discover_ontology = self.llm.generate_structured(
                system_prompt=system_prompt, prompt=user_prompt,
                response_model=OntologyWiringSchema, temperature=0.1
            )
            for edge in discover_ontology.proposed_edges:
                if edge.weight < low_similarity: continue
                cypher = """
                    MATCH (src:Skill) WHERE src.id_node = $src_id OR src.name = $src_id
                    MATCH (tgt:Skill) WHERE tgt.id_node = $tgt_id OR tgt.name = $tgt_id
                    MERGE (src)-[r:ALTERNATIVE_TO]->(tgt)
                    SET r.similarity = $weight
                """
                self.graph.query(cypher, {"src_id": edge.source_node_id, "tgt_id": edge.target_node_id, "weight": edge.weight})
                logger.info(f"[AUTO-WIRING] {edge.source_node_id} ➔ ALTERNATIVE_TO ➔ {edge.target_node_id}")
        except Exception as e:
            logger.error(f"Error wiring Skill ontology: {e}")

    def wire_skillgroup_skill_ontology(self, low_similarity: float = 0.5, threshold: int = 1):
        """Create relationship between SkillGroup and Skill nodes with BELONGS_TO (Incremental)."""
        query_groups = "MATCH (n: SkillGroup) RETURN n.id_node, n.name"
        query_unwired_skills = "MATCH (n: Skill) WHERE NOT (n)-[:BELONGS_TO]->(:SkillGroup) RETURN n.id_node, n.name"
        
        groups = [{"id": node[0], "group": node[1]} for node in self.graph.query(query_groups).result_set]
        unwired_skills = [{"id": node[0], "skill": node[1]} for node in self.graph.query(query_unwired_skills).result_set]
        
        logger.info(f"Found {len(groups)} SkillGroups, {len(unwired_skills)} unwired Skills.")

        if len(unwired_skills) < threshold: 
            logger.info(f"Not enough unwired Skill nodes (Threshold: {threshold}). Skipping.")   
            return

        system_prompt = "You are an IT expert. Group the following unwired Skills into logical SkillGroups (e.g., Database, Frontend, Backend, DevOps). Use concise standard names."
        user_prompt = f"""
        Existing SkillGroups (Optional to use): {groups}
        Unwired Skills (Sources): {unwired_skills}

        Assign each Unwired Skill to an appropriate SkillGroup name. You may invent new SkillGroup names if needed.
        - CRITICAL: Use the exact 'id' field from the 'Unwired Skills' list above for 'source_id'. Do NOT use the skill name.
        """
        try:
            discover_ontology = self.llm.generate_structured(
                system_prompt=system_prompt, prompt=user_prompt,
                response_model=AutoClusterSchema, temperature=0.1
            )
            for cluster in discover_ontology.clusters:
                group_id = f"group_{cluster.group_name.lower().replace(' ', '_').replace('-', '_')}"
                cypher = """
                    MATCH (src:Skill) WHERE src.id_node = $src_id OR src.name = $src_id
                    MERGE (tgt:SkillGroup {id_node: $tgt_id})
                    ON CREATE SET tgt.name = $group_name, tgt.labels = ['SkillGroup']
                    MERGE (src)-[r:BELONGS_TO]->(tgt)
                    SET r.similarity = 1.0
                """
                self.graph.query(cypher, {
                    "src_id": cluster.source_id, 
                    "tgt_id": group_id, 
                    "group_name": cluster.group_name
                })
                logger.info(f"[AUTO-CLUSTERING] {cluster.source_id} ➔ BELONGS_TO ➔ {group_id} ({cluster.group_name})")
        except Exception as e:
            logger.error(f"Error wiring SkillGroup ontology: {e}")

    def wire_company_industry_ontology(self, low_similarity: float = 0.5, threshold: int = 1):
        """Create relationship between Company and Industry nodes with BELONGS_TO (Incremental)."""
        query_inds = "MATCH (n: Industry) RETURN n.id_node, n.name"
        query_unwired_comps = "MATCH (n: Company) WHERE NOT (n)-[:BELONGS_TO]->(:Industry) RETURN n.id_node, n.name"
        
        inds = [{"id": node[0], "industry": node[1]} for node in self.graph.query(query_inds).result_set]
        unwired_comps = [{"id": node[0], "company": node[1]} for node in self.graph.query(query_unwired_comps).result_set]
        
        logger.info(f"Found {len(inds)} Industries, {len(unwired_comps)} unwired Companies.")

        if len(unwired_comps) < threshold: 
            logger.info(f"Not enough unwired Company nodes (Threshold: {threshold}). Skipping.")
            return

        system_prompt = "You are a corporate expert. Group the following unwired Companies into logical Industries (e.g., IT, Finance, Healthcare). Use concise standard names."
        user_prompt = f"""
        Existing Industries (Optional to use): {inds}
        Unwired Companies (Sources): {unwired_comps}

        Assign each Unwired Company to an appropriate Industry name. You may invent new Industry names if needed.
        - CRITICAL: Use the exact 'id' field from the 'Unwired Companies' list above for 'source_id'. Do NOT use the company name.
        """
        try:
            discover_ontology = self.llm.generate_structured(
                system_prompt=system_prompt, prompt=user_prompt,
                response_model=AutoClusterSchema, temperature=0.1
            )
            for cluster in discover_ontology.clusters:
                group_id = f"ind_{cluster.group_name.lower().replace(' ', '_').replace('-', '_')}"
                cypher = """
                    MATCH (src:Company) WHERE src.id_node = $src_id OR src.name = $src_id
                    MERGE (tgt:Industry {id_node: $tgt_id})
                    ON CREATE SET tgt.name = $group_name, tgt.labels = ['Industry']
                    MERGE (src)-[r:BELONGS_TO]->(tgt)
                    SET r.similarity = 1.0
                """
                self.graph.query(cypher, {
                    "src_id": cluster.source_id, 
                    "tgt_id": group_id, 
                    "group_name": cluster.group_name
                })
                logger.info(f"[AUTO-CLUSTERING] {cluster.source_id} ➔ BELONGS_TO ➔ {group_id} ({cluster.group_name})")
        except Exception as e:
            logger.error(f"Error wiring Company-Industry ontology: {e}")
