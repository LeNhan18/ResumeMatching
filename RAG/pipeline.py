import logging
from typing import List, Dict, Any, Optional
from PARSING.ParsingDocument import parse_document
from LLM.client import LLMClient
from RAG.schemas import CVSchema, JDSchema, ScoringWeights, ScoringResult
from RAG.vector_db import VectorDBClient, EmbeddingService
from RAG.matching import hard_match, Reranker
from RAG.scoring import LLMScorer
from GRAPHRAG.query_expansion import QueryExpander
from GRAPHRAG.falkordb_graph import FalkorDBGraph
from GRAPHRAG.graph_extractor import GraphExtractor
from GRAPHRAG.ontology_wire import OntologyWire
from utils.logger import setup_logger

logger = setup_logger("Pipeline", log_file="pipeline.log")

class CVMatcherPipeline:
    def __init__(self):
        # Initialize sub-modules
        self.llm_client = LLMClient()
        self.embedding_service = EmbeddingService(self.llm_client)
        self.vector_db = VectorDBClient(self.embedding_service)
        self.scorer = LLMScorer(self.llm_client)
        
        # Initialize Graph DB once and pass it to components
        self.falkor_db = FalkorDBGraph()
        self.expander = QueryExpander(self.falkor_db)
        self.reranker = Reranker(self.falkor_db)
        self.graph_extractor = GraphExtractor(self.llm_client, self.falkor_db)
        logger.info("CVMatcherPipeline initialized successfully.")

    def ingest_cv(self, file_path: str, cv_id: str) -> CVSchema:
        """
        Parses a CV document, extracts structured fields using LLM, 
        and indexes it into the vector database.
        """
        logger.info(f"Ingesting CV from file: {file_path} (ID: {cv_id})")
        # 1. Parse raw text from file (native PDF, docx, etc.)
        cv_text = parse_document(file_path)
        if not cv_text.strip():
            raise ValueError(f"Extracted text from CV is empty for file: {file_path}")

        # 2. Call LLM to convert raw text into a structured Pydantic Schema
        system_prompt = (
            "You are a professional HR data extraction system. You extract candidate information "
            "from raw CV text into a structured JSON schema. Standardize work experience date ranges "
            "into 'YYYY-MM' or 'YYYY' format. For ongoing jobs, write 'Present'.\n"
            "CRITICAL classification rule for each item in the 'experience' list:\n"
            "- If an item represents a full-time, part-time, or contract job at an actual company, startup, or organization, classify its experience_type as 'Corporate'.\n"
            "- If it is a trainee, intern, or apprenticeship role at a company, classify its experience_type as 'Internship'.\n"
            "- If it is freelance work, self-employment, or contracted freelance, classify its experience_type as 'Freelance'.\n"
            "- If it is a personal pet project, self-study project, or side hustle, classify its experience_type as 'Personal Project'.\n"
            "- If it is a university assignment, graduation thesis, lab project, or course homework, classify its experience_type as 'Academic Project'.\n"
            "Be very careful and look at section headers (e.g., 'PROJECTS', 'DỰ ÁN' vs 'WORK EXPERIENCE', 'KINH NGHIỆM') in the CV to classify correctly."
        )
        prompt = (
            f"Please extract all details from this candidate's CV text into the requested schema.\n\n"
            f"CV TEXT:\n"
            f"---\n"
            f"{cv_text}\n"
            f"---"
        )
        
        cv_schema: CVSchema = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=CVSchema,
            system_prompt=system_prompt
        )
        logger.info(f"Structured CV extraction completed for: {cv_schema.name}")

        # 3. Save to vector DB (which indexes dense + sparse and stores CV payload)
        # We serialize the Pydantic schema into a dictionary to store in payload
        cv_payload = cv_schema.model_dump()
        cv_payload["file_path"] = file_path
        self.vector_db.upsert_cv(cv_id, cv_text, cv_payload)
        
        # 4. Extract and Save to Graph DB (FalkorDB)
        logger.info(f"Extracting Knowledge Graph for candidate {cv_id}...")
        self.graph_extractor.extract_graph_from_cv(cv_text, document_id=cv_id, auto_save=True)
        
        return cv_schema

    def ingest_jd(self, file_path_or_text: str) -> JDSchema:
        """
        Ingests a JD (either raw text or path to a document), 
        and extracts structured requirements using LLM.
        """
        # Detect if input is a file path or direct text
        import os
        if os.path.exists(file_path_or_text):
            logger.info(f"Ingesting JD from file: {file_path_or_text}")
            jd_text = parse_document(file_path_or_text)
        else:
            logger.info("Ingesting JD from direct text block.")
            jd_text = file_path_or_text
            
        if not jd_text.strip():
            raise ValueError("Provided Job Description (JD) text is empty.")

        # Call LLM to extract JD structured requirements
        system_prompt = (
            "You are an expert HR and Technical Recruiter. You extract structured job requirements "
            "from raw JD text into a precise JSON schema. "
            "CRITICAL RULES FOR SKILLS:\n"
            "1. Scrape EVERY SINGLE tool, software, technology, language, framework, and AI model mentioned "
            "(e.g., ChatGPT, Claude, Gemini, n8n, Make, Python, React, AWS) and put them in `required_skills` (or `nice_to_have`).\n"
            "2. Do not generalize tools (e.g., do not write 'AI Tools' if the JD says 'ChatGPT, Claude' - write 'ChatGPT', 'Claude' explicitly).\n"
            "3. MUST BE SHORT KEYWORDS ONLY. DO NOT output full sentences (e.g., write 'ChatGPT' instead of 'Practical understanding of AI tools such as ChatGPT').\n"
            "CRITICAL RULES FOR EXPERIENCE:\n"
            "1. Extract the minimum years of experience exactly. If it says 'Fresher' or 'Intern', set min_exp_years to 0.0."
        )
        prompt = (
            f"Please extract all granular details from this Job Description (JD) text into the requested schema.\n"
            f"Pay special attention to extracting every specific software tool or AI model into the skills lists.\n\n"
            f"JD TEXT:\n"
            f"---\n"
            f"{jd_text}\n"
            f"---"
        )
        
        jd_schema: JDSchema = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=JDSchema,
            system_prompt=system_prompt
        )
        logger.info(f"Structured JD extraction completed for position: {jd_schema.position}")
        logger.info(f"Extracted JD Output: {jd_schema.model_dump_json(indent=2)}")
        
        # Keyword Discovery: Seed missing JD skills into Graph and trigger Ontology Wiring
        self._seed_jd_keywords_to_graph(jd_schema)
        
        return jd_schema

    def _seed_jd_keywords_to_graph(self, jd: JDSchema):
        """
        Keyword Discovery Trigger.
        
        Checks which skills from the JD don't yet exist in the Knowledge Graph,
        creates orphan Skill nodes for them, then triggers JIT Ontology Wiring
        so the LLM can connect them to existing nodes (ALTERNATIVE_TO, BELONGS_TO).
        
        This solves the Cold Start problem: the Graph learns from JD demand signals,
        not just from CV supply.
        """
        import re
        
        all_jd_skills = list(set(jd.required_skills + jd.nice_to_have))
        if not all_jd_skills:
            logger.info("[KeywordDiscovery] No skills in JD to seed.")
            return
            
        graph = self.falkor_db.graph
        
        # Step 1: Check which skills already exist in the Graph (case-insensitive)
        existing_names = set()
        try:
            result = graph.query("MATCH (s:Skill) RETURN toLower(s.name)")
            for row in result.result_set:
                if row[0]:
                    existing_names.add(row[0])
        except Exception as e:
            logger.error(f"[KeywordDiscovery] Error querying existing skills: {e}")
            return
        
        # Step 2: Filter out skills that are already in the Graph
        missing_skills = []
        for skill in all_jd_skills:
            skill_clean = skill.strip()
            if not skill_clean:
                continue
            if skill_clean.lower() not in existing_names:
                missing_skills.append(skill_clean)
        
        if not missing_skills:
            logger.info(f"[KeywordDiscovery] All {len(all_jd_skills)} JD skills already exist in Graph. No seeding needed.")
            return
            
        logger.info(f"[KeywordDiscovery] Found {len(missing_skills)} missing skills to seed: {missing_skills}")
        
        # Step 3: Create orphan Skill nodes for each missing skill
        seeded_count = 0
        for skill_name in missing_skills:
            # Generate deterministic ID consistent with EntityResolver convention
            slug = skill_name.lower().replace(" ", "_").replace(".", "").replace("-", "_").replace("/", "_")
            slug = re.sub(r'_+', '_', slug)
            skill_id = f"skill_{slug}"
            
            try:
                cypher = """
                MERGE (s:Skill {id: $skill_id})
                ON CREATE SET s.name = $skill_name, s.id_node = $skill_id, s.source = 'jd_discovery'
                """
                graph.query(cypher, {"skill_id": skill_id, "skill_name": skill_name})
                seeded_count += 1
                logger.info(f"[KeywordDiscovery] Seeded orphan node: Skill('{skill_name}', id='{skill_id}')")
            except Exception as e:
                logger.error(f"[KeywordDiscovery] Error seeding skill '{skill_name}': {e}")
        
        logger.info(f"[KeywordDiscovery] Seeded {seeded_count}/{len(missing_skills)} new Skill nodes.")
        
        # Step 4: Trigger JIT Ontology Wiring with threshold=1 to connect the orphan nodes
        if seeded_count > 0:
            try:
                logger.info("[KeywordDiscovery] Triggering JIT Ontology Wiring for newly seeded skills...")
                wirer = OntologyWire()
                wirer.wire_skill_ontology(threshold=1)
                wirer.wire_skillgroup_skill_ontology(threshold=1)
                logger.info("[KeywordDiscovery] Ontology Wiring complete.")
            except Exception as e:
                logger.error(f"[KeywordDiscovery] Ontology Wiring failed (non-blocking): {e}")

    def match_cv_to_jd(self, cv_id: str, jd: JDSchema, weights: Optional[ScoringWeights] = None) -> ScoringResult:
        """
        Retrieves a single CV by ID, matches it against a structured JD, and scores it.
        """
        if not weights:
            weights = ScoringWeights() # Use defaults

        # 1. Fetch CV payload
        cv_payload = self.vector_db.get_cv(cv_id)
        if not cv_payload:
            raise KeyError(f"CV with ID '{cv_id}' not found in database.")
            
        # Reconstruct CVSchema
        cv = CVSchema.model_validate(cv_payload)

        # 2. Run Hard-matching (Layer 5)
        hard_match_res = hard_match(cv, jd)

        # 3. Calculate dense soft-match score
        # For a single CV, we can fetch its stored dense vector and compute similarity with JD embedding
        jd_text = f"{jd.position} {jd.domain} {' '.join(jd.required_skills)} {jd.industry}"
        jd_embedding = self.embedding_service.get_dense_embedding(jd_text)
        
        # We need the dense vector of the CV. If running in-memory, we can read it.
        # Otherwise, if in Qdrant, we could retrieve the vector.
        # To make it simple and unified:
        # We calculate similarity using the text stored in CV payload against JD text.
        cv_text = cv_payload.get("extracted_text", "")
        cv_embedding = self.embedding_service.get_dense_embedding(cv_text)
        
        # Calculate cosine similarity (dot product of normalized vectors)
        soft_match_score = 0.5
        if len(cv_embedding) == len(jd_embedding):
            cosine_sim = sum(q * d for q, d in zip(jd_embedding, cv_embedding))
            # Normalize to 0-1
            soft_match_score = max(0.0, min(1.0, (cosine_sim + 1.0) / 2.0))

        # 4. Perform qualitative scoring (Layer 6)
        # Note: Cho hàm match_cv_to_jd (Single Match), chúng ta bypass Graph Insights để giữ luồng cơ bản.
        scoring_res = self.scorer.score_candidate(cv, jd, hard_match_res, soft_match_score, weights, graph_insights=[])
        return scoring_res

    def rank_candidates(self, jd_text_or_file: str, weights: Optional[ScoringWeights] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Extracts JD, runs hybrid search across indexed candidates, 
        reranks the candidates, and runs LLM evaluation on the top matches.
        """
        if not weights:
            weights = ScoringWeights()

        # 1. Extract JD structure
        jd = self.ingest_jd(jd_text_or_file)
        
        # Prepare query enriched string representing the JD
        query_str = self.expander.build_enriched_query(jd)
        logger.info(f"Graph Expanded Query: {query_str}")
        
        # 2. Hybrid search across Vector DB
        # We search with industry filter if relevant, otherwise global
        metadata_filter = None
        # Optional: metadata_filter = {"industry": jd.industry}
        
        logger.info(f"Retrieving candidate matches for query: '{query_str}'")
        search_hits = self.vector_db.search_cv(query_str, limit=limit * 3, metadata_filter=metadata_filter)
        
        if not search_hits:
            logger.info("No candidates found in vector search.")
            return []

        # 3. Re-rank candidates (Cross-Encoder / Heuristic + Graph)
        reranked_hits = self.reranker.rerank(query_str, search_hits, jd=jd, limit=limit)
        
        # 4. Match and score the top candidates
        ranked_results = []
        for hit in reranked_hits:
            cv_id = hit["id"]
            cv_payload = hit["payload"]
            soft_score = hit.get("rerank_score", 0.5)
            
            cv = CVSchema.model_validate(cv_payload)
            
            # Run Hard match
            hard_match_res = hard_match(cv, jd)
            
            # Run Scorer
            graph_insights = hit.get("graph_insights", [])
            scoring_res = self.scorer.score_candidate(cv, jd, hard_match_res, soft_score, weights, graph_insights)
            
            ranked_results.append({
                "candidate_id": cv_id,
                "candidate_name": cv.name,
                "score": scoring_res.match_score,
                "breakdown": scoring_res.breakdown.model_dump(),
                "hard_match": hard_match_res,
                "strengths": scoring_res.strengths,
                "missing_skills": scoring_res.missing_skills,
                "reasoning": scoring_res.reasoning
            })
            
        # Re-sort final list by actual qualitative match score
        ranked_results.sort(key=lambda x: x["score"], reverse=True)
        return ranked_results
