import logging
from typing import Dict, Any
from pydantic import BaseModel, Field
from LLM.client import LLMClient
from RAG.schemas import CVSchema, JDSchema, ScoringWeights, ScoringResult, ScoringBreakdown
from utils.logger import setup_logger

logger = setup_logger("Scoring", log_file="scoring.log")

class LLMScorer:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def score_candidate(
        self, 
        cv: CVSchema, 
        jd: JDSchema, 
        hard_match_res: Dict[str, Any], 
        soft_match_score: float, 
        weights: ScoringWeights,
        graph_insights: list[str] = None
    ) -> ScoringResult:
        """
        Runs qualitative scoring on a CV against a JD.
        The LLM rates individual breakdown categories, and Python calculates the deterministic weighted score.
        """
        # Format academic degrees string to avoid backslashes inside f-strings (Python < 3.12 compatibility)
        edu_list = []
        for edu in cv.education:
            deg = edu.degree or "Degree"
            maj = edu.major or "Major"
            sch = edu.school or "Unknown School"
            edu_list.append(f"{deg} in {maj} ({sch})")
        edu_str = ", ".join(edu_list) or "None"

        # Formulate LLM prompt containing parsed data and matching context
        prompt = (
            f"Please evaluate the candidate's CV against the Job Description (JD).\n\n"
            f"### JOB DESCRIPTION (JD) REQUIREMENTS:\n"
            f"- Position: {jd.position}\n"
            f"- Industry/Domain: {jd.industry} / {jd.domain}\n"
            f"- Target Level: {jd.level}\n"
            f"- Min Experience: {jd.min_exp_years} years\n"
            f"- Required Skills: {', '.join(jd.required_skills)}\n"
            f"- Nice to Have: {', '.join(jd.nice_to_have)}\n"
            f"- Education Requirement: {jd.education_requirement or 'None'}\n\n"
            
            f"### CANDIDATE CV SUMMARY:\n"
            f"- Name: {cv.name}\n"
            f"- Summary: {cv.summary or 'None'}\n"
            f"- Industry: {cv.industry or 'Unknown'}\n"
            f"- Academic Degrees: {edu_str}\n"
            f"- General Skills: {', '.join(cv.skills)}\n"
            f"- Certifications: {', '.join(cv.certs) or 'None'}\n"
            f"- Languages: {', '.join(cv.languages) or 'None'}\n\n"
            
            f"### CANDIDATE WORK HISTORY:\n"
        )
        
        for idx, exp in enumerate(cv.experience):
            prompt += (
                f"{idx+1}. Company: {exp.company} | Position: {exp.position} | "
                f"Seniority: {exp.seniority_level} | Duration: {exp.start_date} to {exp.end_date or 'Present'}\n"
                f"   - Technologies: {', '.join(exp.skills_used)}\n"
                f"   - Description: {exp.description or 'None'}\n"
            )
            
        prompt += (
            f"\n### MATCHING METRICS (LAYER 5):\n"
            f"- Deterministic Relevant Experience: {hard_match_res['relevant_years']} years (JD requested: {hard_match_res['required_years']} years)\n"
            f"- Experiencing Hard-Filter Passed: {hard_match_res['exp_passed']}\n"
            f"- Matched Required Skills: {', '.join(hard_match_res['matched_required_skills']) or 'None'}\n"
            f"- Missing Required Skills: {', '.join(hard_match_res['missing_required_skills']) or 'None'}\n"
            f"- Vector Soft-Match Relevance: {soft_match_score:.2f} (scale 0-1)\n"
            f"- English Language Proficiency Detected: {hard_match_res.get('has_english', False)}\n"
            f"- Practical Industry Experience: {hard_match_res.get('practical_years', 0.0)} years (excluding academic/intern/freelance assignments)\n"
            f"- Has Practical Industry Experience: {hard_match_res.get('has_practical_exp', False)}\n\n"
            
            f"### SYSTEM SCORING PRIORITIES:\n"
            f"1. **PRIORITIZE COMPANY EXPERIENCE**: Candidates with actual corporate employment history at companies (full-time or contract roles, clear job descriptions) must be scored significantly higher in the 'experience' category. Candidates whose history consists only of personal projects, academic/university assignments, or self-study/pet projects must be penalized and scored under 50/100 for 'experience', even if they have many projects.\n"
            f"2. **PRIORITIZE ENGLISH CERTIFICATES**: Candidates who have verified English certificates (such as IELTS, TOEIC, TOEFL, PTE, CEFR, etc.) must receive a significant positive boost (e.g., +10 to +15 points in the education or culture/suitability categories) compared to candidates without certified proof. You must explicitly list this certificate in their 'strengths' list.\n"
        )
        
        if graph_insights:
            prompt += "\n### KNOWLEDGE GRAPH INSIGHTS (LAYER 5.5):\n"
            for insight in graph_insights:
                prompt += f"- {insight}\n"
            prompt += "\nUse these graph insights to write Strengths and to justify the Skills and Experience scores. Do NOT penalize missing skills if the graph found an alternative.\n\n"
        else:
            prompt += "\n"
            
        prompt += (
            f"### SCORING RUBRIC (Rate each category out of 100):\n"
            f"1. Skills Score: Technical overlap, expertise depth, usage of skills in past jobs.\n"
            f"2. Experience Score: Industry tenure, career progression (e.g. Junior -> Mid -> Senior), job stability, domain expertise.\n"
            f"3. Education Score: Academic degrees, certification relevance.\n"
            f"4. Culture Fit Score: Soft skills, career summary tone, general adaptability.\n\n"
            
            f"IMPORTANT: Evaluate the candidate objectively. Provide scores based on evidence. "
            f"Identify actual strengths and real missing skills."
        )

        system_prompt = (
            "You are an expert HR AI Assessor. Provide objective scoring evaluations for candidate CVs against Job Descriptions. "
            "You MUST output structured JSON rating the candidate in the four categories (skills, experience, education, culture_fit), "
            "along with a list of missing_skills, strengths, and detailed justification reasoning.\n"
            "CRITICAL: Write all qualitative text fields ('reasoning_skills', 'reasoning_experience', 'strengths', 'missing_skills', etc.) in Vietnamese (Tiếng Việt). "
            "Keep technical terms (e.g. Python, Docker, FastAPI, ReactJS, SQL, RAG) in their original English form without translation.\n"
            "Note: Do not output 'match_score' directly as it is calculated deterministically by our framework; "
            "focus on rating the categories (0 to 100) and providing qualitative notes.\n"
            "COT RULE: You MUST think step-by-step. Provide your detailed analytical reasoning for a category BEFORE outputting the numerical score for that category."
        )
        
        if graph_insights:
            system_prompt += (
                "\nCRITICAL XAI RULE: Do not penalize the candidate or list a skill as 'missing_skills' "
                "if the KNOWLEDGE GRAPH INSIGHTS explicitly states they possess an alternative/equivalent skill. "
                "You must list these graph insights in the 'strengths' and 'reasoning' arrays."
            )

        # Temporary Pydantic schema for LLM output (excludes final match_score calculation)
        class LLMScoringResponse(BaseModel):
            reasoning_skills: str = Field(description="Phân tích kỹ năng trước khi chấm điểm")
            skills: float = Field(description="Điểm kỹ năng (0-100)")
            reasoning_experience: str = Field(description="Phân tích kinh nghiệm làm việc trước khi chấm điểm")
            experience: float = Field(description="Điểm kinh nghiệm (0-100)")
            reasoning_education: str = Field(description="Phân tích học vấn trước khi chấm điểm")
            education: float = Field(description="Điểm học vấn (0-100)")
            reasoning_culture: str = Field(description="Phân tích độ phù hợp văn hóa trước khi chấm điểm")
            culture_fit: float = Field(description="Điểm phù hợp văn hóa (0-100)")
            missing_skills: list[str]
            strengths: list[str]

        try:
            logger.info(f"Invoking LLM Scorer for candidate: {cv.name}")
            raw_evaluation = self.llm_client.generate_structured(
                prompt=prompt,
                response_model=LLMScoringResponse,
                system_prompt=system_prompt
            )
            
            # 2. Deterministic calculation of the final match score
            skills_score = raw_evaluation.skills
            exp_score = raw_evaluation.experience
            edu_score = raw_evaluation.education
            culture_score = raw_evaluation.culture_fit
            
            weighted_score = (
                (skills_score * weights.skills) +
                (exp_score * weights.experience) +
                (edu_score * weights.education) +
                (culture_score * weights.culture_fit)
            )
            
            # Ensure final score is between 0 and 100 and rounded to 1 decimal place
            final_score = round(max(0.0, min(100.0, weighted_score)), 1)
            
            # Assemble full response schema
            breakdown = ScoringBreakdown(
                skills=skills_score,
                experience=exp_score,
                education=edu_score,
                culture_fit=culture_score
            )
            
            reasoning_combined = (
                f"**Skills:** {raw_evaluation.reasoning_skills}\n"
                f"**Experience:** {raw_evaluation.reasoning_experience}\n"
                f"**Education:** {raw_evaluation.reasoning_education}\n"
                f"**Culture Fit:** {raw_evaluation.reasoning_culture}"
            )
            
            result = ScoringResult(
                match_score=final_score,
                breakdown=breakdown,
                missing_skills=raw_evaluation.missing_skills,
                strengths=raw_evaluation.strengths,
                reasoning=reasoning_combined
            )
            
            logger.info(f"Finished qualitative scoring. Final Match Score: {result.match_score}%")
            return result
            
        except Exception as e:
            logger.error(f"Error during LLM scoring evaluation: {e}. Returning default baseline scores.")
            # Graceful fallback in case of API outages
            base_score = 50.0
            breakdown = ScoringBreakdown(skills=base_score, experience=base_score, education=base_score, culture_fit=base_score)
            return ScoringResult(
                match_score=base_score,
                breakdown=breakdown,
                missing_skills=hard_match_res.get("missing_required_skills", []),
                strengths=["Data successfully ingested"],
                reasoning=f"Evaluation fell back to default baseline due to LLM error: {e}"
            )
