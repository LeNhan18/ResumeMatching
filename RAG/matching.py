import os
import re
import math
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from RAG.schemas import CVSchema, JDSchema
from GRAPHRAG.falkordb_graph import FalkorDBGraph
from utils.logger import setup_logger

logger = setup_logger("Matching", log_file="matching.log")

# =====================================================================
# 1. Date Utility Functions for Work Experience Calculations
# =====================================================================

def parse_date_string(date_str: Optional[str]) -> datetime:
    """Parses a wide range of date formats found in CVs into datetime objects."""
    if not date_str:
        return datetime.now()
        
    clean_str = date_str.strip().lower()
    
    # Common words representing ongoing employment
    present_markers = ["present", "current", "now", "đang làm", "nay", "hiện tại", "hiện nay", "tới nay"]
    if any(marker in clean_str for marker in present_markers):
        return datetime.now()
        
    # Normalize delimiters like spaces, slashes, backslashes, dots, dashes
    clean_str = re.sub(r'[\s./\\]+', '-', clean_str)
    
    # Try YYYY-MM
    try:
        return datetime.strptime(clean_str, "%Y-%m")
    except ValueError:
        pass
        
    # Try MM-YYYY (e.g. 05-2021)
    try:
        parts = clean_str.split('-')
        if len(parts) == 2 and len(parts[1]) == 4:
            return datetime.strptime(clean_str, "%m-%Y")
    except ValueError:
        pass
        
    # Try YYYY (e.g. 2020)
    try:
        if len(clean_str) == 4 and clean_str.isdigit():
            # Assume January of that year
            return datetime(int(clean_str), 1, 1)
    except ValueError:
        pass
        
    # Try DD-MM-YYYY
    try:
        return datetime.strptime(clean_str, "%d-%m-%Y")
    except ValueError:
        pass
        
    # Fallback default
    logger.debug(f"Could not parse date string: '{date_str}', defaulting to current time.")
    return datetime.now()

def calculate_duration_months(start_str: str, end_str: Optional[str]) -> float:
    """Calculates duration in months between two date strings."""
    try:
        start_date = parse_date_string(start_str)
        end_date = parse_date_string(end_str)
        
        delta = end_date - start_date
        # Use average days in a month (365.25 / 12)
        months = delta.days / 30.4375
        return max(0.0, months)
    except Exception as e:
        logger.error(f"Error calculating duration between '{start_str}' and '{end_str}': {e}")
        return 0.0


# =====================================================================
# 2. Hard-matching (Layer 5 - Deterministic Logic)
# =====================================================================

def hard_match(cv: CVSchema, jd: JDSchema) -> Dict[str, Any]:
    """
    Evaluates rule-based constraints between CV and JD.
    Returns details on experience duration, certification status, and skill matches.
    """
    # 1. Calculate relevant experience duration
    # We sum months of experience where the job uses skills required in JD,
    # or belongs to the target domain, or where the job title matches the domain.
    total_relevant_months = 0.0
    jd_req_skills_set = {s.lower() for s in jd.required_skills}
    jd_nice_skills_set = {s.lower() for s in jd.nice_to_have}
    all_target_skills = jd_req_skills_set.union(jd_nice_skills_set)
    jd_domain = jd.domain.lower()
    
    academic_or_freelance_keywords = [
        "freelance", "tự do", "personal", "cá nhân", "project", "dự án", "đồ án", "bài tập", 
        "self-study", "tự học", "tự làm", "pet project", "student", "học sinh", "sinh viên", 
        "học viên", "graduation", "thesis", "luận văn", "tốt nghiệp"
    ]

    for exp in cv.experience:
        comp = exp.company.lower()
        pos = exp.position.lower()
        desc = exp.description.lower() if exp.description else ""
        
        # Exclude personal/academic projects and freelance work from core experience calculations
        is_academic_or_freelance = False
        if hasattr(exp, "experience_type") and exp.experience_type:
            is_academic_or_freelance = exp.experience_type in ["Freelance", "Personal Project", "Academic Project"]
        else:
            is_academic_or_freelance = any(kw in comp or kw in pos or kw in desc for kw in academic_or_freelance_keywords)
            
        if is_academic_or_freelance:
            continue
            
        exp_skills = {s.lower() for s in exp.skills_used}
        exp_position = exp.position.lower()
        
        is_relevant = False
        
        # Criteria A: Overlap in skills used
        if exp_skills.intersection(all_target_skills):
            is_relevant = True
            
        # Criteria B: Position title or description contains domain keywords
        elif jd_domain in exp_position or (exp.description and jd_domain in exp.description.lower()):
            is_relevant = True
            
        # Criteria C: Industry match
        elif cv.industry and jd.industry and cv.industry.lower() == jd.industry.lower():
            is_relevant = True
            
        if is_relevant:
            duration = calculate_duration_months(exp.start_date, exp.end_date)
            total_relevant_months += duration

    relevant_years = round(total_relevant_months / 12.0, 1)
    exp_passed = relevant_years >= jd.min_exp_years

    # 2. Verify mandatory skills overlap
    cv_skills_set = {s.lower() for s in cv.skills}
    # Add skills mentioned in work experiences to general skills
    for exp in cv.experience:
        cv_skills_set.update(s.lower() for s in exp.skills_used)
        
    matched_required = set()
    for req_skill in jd_req_skills_set:
        req_skill_lower = req_skill.lower()
        if req_skill_lower in cv_skills_set:
            matched_required.add(req_skill)
        else:
            # Check if any CV skill token is contained within the JD required skill as a standalone word
            for cv_skill in cv_skills_set:
                escaped_cv = re.escape(cv_skill)
                if re.search(r'\b' + escaped_cv + r'\b', req_skill_lower):
                    matched_required.add(req_skill)
                    break
                    
    required_skills_ratio = len(matched_required) / len(jd_req_skills_set) if jd_req_skills_set else 1.0
    skills_passed = required_skills_ratio >= 0.5  # E.g. Candidate must have at least 50% of required skills to pass hard filter

    # 3. Verify education requirements if any
    edu_passed = True
    if jd.education_requirement:
        edu_req = jd.education_requirement.lower()
        # Find highest degree of candidate
        candidate_degrees = [edu.degree.lower() for edu in cv.education if edu.degree]
        
        if "master" in edu_req or "thạc sĩ" in edu_req:
            edu_passed = any("master" in d or "thạc sĩ" in d or "phd" in d or "tiến sĩ" in d for d in candidate_degrees)
        elif "phd" in edu_req or "tiến sĩ" in edu_req:
            edu_passed = any("phd" in d or "tiến sĩ" in d for d in candidate_degrees)
        elif "bachelor" in edu_req or "cử nhân" in edu_req or "kỹ sư" in edu_req or "engineer" in edu_req:
            edu_passed = any("bachelor" in d or "cử nhân" in d or "kỹ sư" in d or "engineer" in d or "master" in d or "phd" in d for d in candidate_degrees)

    # 4. Check English language proficiency (ONLY count specific certificates: IELTS, TOEIC, TOEFL, B1, A1, CEFR, CEFT, etc.)
    has_english = False
    english_cert_keywords = ["ielts", "toeic", "toefl", "pte", "cefr", "ceft", "a1", "a2", "b1", "b2", "c1", "c2"]
    for lang in cv.languages:
        if any(kw in lang.lower() for kw in english_cert_keywords):
            has_english = True
            break
            
    if not has_english:
        for cert in cv.certs:
            if any(kw in cert.lower() for kw in english_cert_keywords):
                has_english = True
                break

    # 5. Calculate practical, non-academic years of experience (includes internships as corporate experience, excludes freelance/personal projects)
    practical_months = 0.0
    academic_or_freelance_keywords = [
        "freelance", "tự do", "personal", "cá nhân", "project", "dự án", "đồ án", "bài tập", 
        "self-study", "tự học", "tự làm", "pet project", "student", "học sinh", "sinh viên", 
        "học viên", "graduation", "thesis", "luận văn", "tốt nghiệp"
    ]
    
    for exp in cv.experience:
        comp = exp.company.lower()
        pos = exp.position.lower()
        desc = exp.description.lower() if exp.description else ""
        
        # Determine if this role qualifies as a full-time or intern industry position (not freelance or academic)
        is_academic_or_freelance = False
        if hasattr(exp, "experience_type") and exp.experience_type:
            is_academic_or_freelance = exp.experience_type in ["Freelance", "Personal Project", "Academic Project"]
        else:
            is_academic_or_freelance = any(kw in comp or kw in pos or kw in desc for kw in academic_or_freelance_keywords)
            
        if not is_academic_or_freelance:
            duration = calculate_duration_months(exp.start_date, exp.end_date)
            practical_months += duration
            
    practical_years = round(practical_months / 12.0, 1)
    has_practical_exp = practical_years >= 1.0  # Has at least 1 year of company experience
    has_worked = practical_months > 0.0         # Has worked at least once in a company (including interns)

    return {
        "exp_passed": exp_passed,
        "skills_passed": skills_passed,
        "education_passed": edu_passed,
        "relevant_years": relevant_years,
        "required_years": jd.min_exp_years,
        "matched_required_skills": list(matched_required),
        "missing_required_skills": list(jd_req_skills_set - cv_skills_set),
        "overall_hard_match_passed": exp_passed and skills_passed and edu_passed and has_worked,
        "has_english": has_english,
        "practical_years": practical_years,
        "has_practical_exp": has_practical_exp,
        "has_worked": has_worked
    }


# =====================================================================
# 3. Soft-matching (Layer 5 - RRF & Re-ranking)
# =====================================================================

def reciprocal_rank_fusion(dense_hits: List[Dict[str, Any]], sparse_hits: List[Dict[str, Any]], k: int = 60) -> List[Dict[str, Any]]:
    """
    Combines dense and sparse search rankings using Reciprocal Rank Fusion (RRF).
    """
    scores = {}
    payloads = {}
    
    # 1. Apply Dense Ranks
    for rank, hit in enumerate(dense_hits):
        doc_id = hit["id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank + 1))
        payloads[doc_id] = hit["payload"]
        
    # 2. Apply Sparse Ranks
    for rank, hit in enumerate(sparse_hits):
        doc_id = hit["id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank + 1))
        if doc_id not in payloads:
            payloads[doc_id] = hit["payload"]
            
    # Convert score mapping to a sorted list of items
    fused = []
    for doc_id, score in scores.items():
        fused.append({
            "id": doc_id,
            "rrf_score": score,
            "payload": payloads[doc_id]
        })
        
    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused

class GraphScorer:
    """Sử dụng Đồ thị Tri thức để tính điểm ngữ nghĩa (Graph-based Semantic Score)."""
    def __init__(self, graph: FalkorDBGraph = None):
        try:
            self.graph = graph.graph if graph else FalkorDBGraph().graph
        except Exception as e:
            logger.error(f"Could not initialize FalkorDBGraph for GraphScorer: {e}")
            self.graph = None

    def calculate_skill_affinity(self, candidate_id: str, jd_skills: List[str]) -> tuple[float, List[str]]:
        """Calculate similarity of skills in CV and JD using Graph anchor"""
        if not self.graph or not candidate_id or not jd_skills: return 0.0, []
        jd_s = [s.lower().strip() for s in jd_skills if s and s.strip()]
        if not jd_s: return 0.0, []

        cypher = """
        MATCH (c:Candidate {id_node: $candidate_id})-[:HAS_SKILL]->(cv_s:Skill)-[r:ALTERNATIVE_TO]-(jd_s:Skill)
        WHERE toLower(jd_s.name) IN $jd_skills
        RETURN cv_s.name, jd_s.name, r.similarity
        """
        try:
            res = self.graph.query(cypher, params={'candidate_id': str(candidate_id), 'jd_skills': jd_s})
            score = 0.0
            insights = []
            if res.result_set:
                for row in res.result_set:
                    cv_skill, jd_skill, sim = row[0], row[1], row[2] if row[2] else 0.5
                    score += sim
                    insights.append(f"Kỹ năng tương đương: Sở hữu '{cv_skill}' có thể thay thế cho '{jd_skill}' (độ tương đồng {sim})")
            return min(0.3, score * 0.1), insights
        except Exception as e:
            logger.error(f"GraphScorer skill error: {e}")
            return 0.0, []

    def check_position_match(self, candidate_id: str, jd_position: str) -> tuple[float, List[str]]:
        """Check equivalent position match using Graph anchor"""
        if not self.graph or not candidate_id or not jd_position: return 0.0, []
        cypher = """
        MATCH (c:Candidate {id_node: $candidate_id})-[:HELD_POSITION]->(cv_p:JobPosition)-[:EQUIVALENT_TO]-(jd_p:JobPosition)
        WHERE toLower(jd_p.name) = $jd_position
        RETURN cv_p.name, jd_p.name
        """
        try:
            res = self.graph.query(cypher, params={'candidate_id': str(candidate_id), 'jd_position': jd_position.lower().strip()})
            insights = []
            if res.result_set:
                count = len(res.result_set)
                for row in res.result_set:
                    insights.append(f"Chức danh tương đương: Đã từng làm '{row[0]}' tương đương với chức danh '{row[1]}' yêu cầu.")
                return (0.3 if count > 0 else 0.0), insights
            return 0.0, []
        except Exception as e:
            logger.error(f"GraphScorer position error: {e}")
            return 0.0, []

    def check_industry_match(self, candidate_id: str, jd_industry: str) -> tuple[float, List[str]]:
        """Check industry match between CV and JD using Graph anchor"""
        if not self.graph or not candidate_id or not jd_industry: return 0.0, []
        cypher = """
        MATCH (c:Candidate {id_node: $candidate_id})-[:WORKED_AT]->(comp:Company)-[:BELONGS_TO]->(i:Industry)
        WHERE toLower(i.name) = $jd_industry
        RETURN comp.name, i.name
        """
        try:
            res = self.graph.query(cypher, params={'candidate_id': str(candidate_id), 'jd_industry': jd_industry.lower().strip()})
            insights = []
            if res.result_set:
                count = len(res.result_set)
                for row in res.result_set:
                    insights.append(f"Ngành nghề phù hợp: Đã làm việc tại công ty '{row[0]}' thuộc mảng '{row[1]}'.")
                return (0.2 if count > 0 else 0.0), insights
            return 0.0, []
        except Exception as e:
            logger.error(f"GraphScorer industry error: {e}")
            return 0.0, []

    def check_major_match(self, candidate_id: str, jd_major: str) -> tuple[float, List[str]]:
        """Check major match between CV and JD using Graph anchor"""
        if not self.graph or not candidate_id or not jd_major: return 0.0, []
        cypher = """
        MATCH (c:Candidate {id_node: $candidate_id})-[:STUDIED_MAJOR]->(cv_m:Major)-[:RELATED_MAJOR]-(jd_m:Major)
        WHERE toLower(jd_m.name) = $jd_major
        RETURN cv_m.name, jd_m.name
        """
        try:
            res = self.graph.query(cypher, params={'candidate_id': str(candidate_id), 'jd_major': jd_major.lower().strip()})
            insights = []
            if res.result_set:
                count = len(res.result_set)
                for row in res.result_set:
                    insights.append(f"Ngành học liên quan: Tốt nghiệp ngành '{row[0]}' được đánh giá liên quan mật thiết với ngành '{row[1]}'.")
                return (0.2 if count > 0 else 0.0), insights
            return 0.0, []
        except Exception as e:
            logger.error(f"GraphScorer major error: {e}")
            return 0.0, []

    def get_graph_score_and_insights(self, candidate_id: str, jd: JDSchema) -> Dict[str, Any]:
        """Runs all sub-metrics to calculate total score and aggregate insights."""
        total_score = 0.0
        all_insights = []
        
        if not self.graph or not candidate_id or not jd:
            return {"total_score": 0.0, "insights": []}
            
        if jd.required_skills:
            score, insights = self.calculate_skill_affinity(candidate_id, jd.required_skills)
            total_score += score
            all_insights.extend(insights)
            
        if jd.position:
            score, insights = self.check_position_match(candidate_id, jd.position)
            total_score += score
            all_insights.extend(insights)
            
        if jd.industry:
            score, insights = self.check_industry_match(candidate_id, jd.industry)
            total_score += score
            all_insights.extend(insights)
            
        if jd.major:
            score, insights = self.check_major_match(candidate_id, jd.major)
            total_score += score
            all_insights.extend(insights)
            
        # Deduplicate insights just in case
        insights_unique = list(set(all_insights))
        return {"total_score": total_score, "insights": insights_unique}

class Reranker:
    """Handles re-ranking candidates using local models, heuristic fallbacks, and Graph DB."""
    def __init__(self, graph_db: FalkorDBGraph = None):
        self.local_model = None
        self.graph_scorer = GraphScorer(graph_db)
        
        if os.getenv("USE_LOCAL_RERANKER", "false").lower() == "true":
            try:
                from sentence_transformers import CrossEncoder
                logger.info("Loading local CrossEncoder reranker (ms-marco-MiniLM)...")
                self.local_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
                logger.info("Local CrossEncoder loaded successfully.")
            except ImportError:
                logger.warning("sentence-transformers not installed. Reranker will run in HEURISTIC mode.")

    def rerank(self, query: str, candidates: List[Dict[str, Any]], jd: JDSchema = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Re-ranks candidates based on direct textual relevance to query (JD)."""
        if not candidates:
            return []
            
        # 1. Use local cross-encoder if loaded
        if self.local_model:
            try:
                pairs = []
                for cand in candidates:
                    cand_text = cand["payload"].get("extracted_text", "")
                    pairs.append([query, cand_text])
                
                scores = self.local_model.predict(pairs)
                for idx, score in enumerate(scores):
                    # Map cross-encoder score to 0-1 range roughly using sigmoid
                    normalized_score = 1.0 / (1.0 + math.exp(-score))
                    candidates[idx]["rerank_score"] = normalized_score
                    
                candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
                return candidates[:limit]
            except Exception as e:
                logger.error(f"Error during cross-encoder reranking: {e}. Falling back to heuristic.")

        # 2. Heuristic & Graph fallback
        return self._heuristic_rerank(query, candidates, jd, limit)

    def _heuristic_rerank(self, query: str, candidates: List[Dict[str, Any]], jd: JDSchema = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Computes a heuristic alignment score based on token overlap & structural fields + Graph."""
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        
        # Normalize sparse scores
        max_sparse = max((cand.get("sparse_score", 0.0) for cand in candidates), default=1.0)
        if max_sparse <= 0.0: max_sparse = 1.0
        
        for cand in candidates:
            payload = cand["payload"]
            cv_text = payload.get("extracted_text", "").lower()
            cv_words = set(re.findall(r'\b\w+\b', cv_text))
            
            # Simple keyword Jaccard overlap
            intersection = query_words.intersection(cv_words)
            union = query_words.union(cv_words)
            jaccard = len(intersection) / len(union) if union else 0.0
            
            # Boost score based on schema overlap
            skills_boost = 0.0
            cv_skills = set(payload.get("skills", []))
            
            # Check for English certificate to apply a strong prioritization boost (+0.15)
            has_english_cert = False
            english_cert_keywords = ["ielts", "toeic", "toefl", "pte", "cefr", "ceft", "a1", "a2", "b1", "b2", "c1", "c2"]
            cv_certs = payload.get("certs", [])
            cv_langs = payload.get("languages", [])
            for cert in cv_certs:
                if any(kw in cert.lower() for kw in english_cert_keywords):
                    has_english_cert = True
                    break
            if not has_english_cert:
                for lang in cv_langs:
                    if any(kw in lang.lower() for kw in english_cert_keywords):
                        has_english_cert = True
                        break
            english_boost = 0.15 if has_english_cert else 0.0

            # Experience priority boost: Corporate Job (+0.25) > Internship (+0.10) > Projects/Freelance (+0.0)
            has_corp_job = False
            has_internship = False
            academic_or_freelance_keywords = [
                "freelance", "tự do", "personal", "cá nhân", "project", "dự án", "đồ án", "bài tập", 
                "self-study", "tự học", "tự làm", "pet project", "student", "học sinh", "sinh viên", 
                "học viên", "graduation", "thesis", "luận văn", "tốt nghiệp"
            ]
            intern_keywords = ["intern", "thực tập", "trainee"]
            
            cv_exp = payload.get("experience", [])
            for exp in cv_exp:
                comp = exp.get("company", "").lower()
                pos = exp.get("position", "").lower()
                desc = exp.get("description", "").lower() if exp.get("description") else ""
                
                is_academic_or_freelance = False
                is_intern = False
                exp_type = exp.get("experience_type")
                if exp_type:
                    is_academic_or_freelance = exp_type in ["Freelance", "Personal Project", "Academic Project"]
                    is_intern = exp_type == "Internship"
                else:
                    is_academic_or_freelance = any(kw in comp or kw in pos or kw in desc for kw in academic_or_freelance_keywords)
                    is_intern = any(kw in comp or kw in pos or kw in desc for kw in intern_keywords)
                    
                if not is_academic_or_freelance:
                    if is_intern:
                        has_internship = True
                    else:
                        has_corp_job = True
            exp_boost = 0.0
            if has_corp_job:
                exp_boost = 0.25
            elif has_internship:
                exp_boost = 0.10

            # Calculate Graph Score (Layer 5.5)
            graph_score = 0.0
            graph_insights = []
            cv_id = cand.get("id")
            
            if jd and cv_id:
                graph_data = self.graph_scorer.get_graph_score_and_insights(cv_id, jd)
                graph_score = graph_data["total_score"]
                graph_insights = graph_data["insights"]
                cand["graph_insights"] = graph_insights

            # Estimate rerank score using dense + sparse + jaccard + heuristics + graph
            dense_score = cand.get("dense_score", 0.5)
            sparse_score = cand.get("sparse_score", 0.0) / max_sparse # Normalized [0, 1]
            
            # Hybrid weighted combination
            cand["rerank_score"] = (dense_score * 0.3) + (sparse_score * 0.2) + (jaccard * 0.1) + (graph_score * 0.4) + english_boost + exp_boost
            
        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        return candidates[:limit]
