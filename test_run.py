import os
import sys
import logging
from RAG.pipeline import CVMatcherPipeline
from RAG.schemas import ScoringWeights

# Reconfigure stdout/stderr to UTF-8 to handle Vietnamese text output safely on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("CVMatcherTest")

def main():
    logger.info("=== STARTING LIVE PDF FILES MATCHING TEST ===")
    
    # Define file paths
    jd_file = "AI ENGINEER JD.pdf"
    cv_file_1 = "HoangThaiAnh_AIEngineer.pdf"
    cv_file_2 = "LeThanhNhanCVTiengViet.pdf"
    
    # Verify JD exists
    if not os.path.exists(jd_file):
        logger.error(f"Required Job Description (JD) file not found in workspace: {jd_file}")
        return
        
    # Collect CVs that exist
    cv_configs = []
    if os.path.exists(cv_file_1):
        cv_configs.append((cv_file_1, "11111111-1111-1111-1111-111111111111"))
    else:
        logger.warning(f"CV file not found (skipping): {cv_file_1}")
        
    if os.path.exists(cv_file_2):
        cv_configs.append((cv_file_2, "22222222-2222-2222-2222-222222222222"))
    else:
        logger.warning(f"CV file not found (skipping): {cv_file_2}")
        
    if not cv_configs:
        logger.error("No candidate CV files found in the workspace to test.")
        return
            
    # Initialize pipeline
    pipeline = CVMatcherPipeline()
    
    # 1. Ingest CVs
    logger.info("--- INGESTING ACTUAL CANDIDATE CVS ---")
    for file_path, cv_id in cv_configs:
        try:
            cv = pipeline.ingest_cv(file_path, cv_id=cv_id)
            logger.info(f"Successfully ingested candidate: {cv.name} | General Skills: {cv.skills}")
        except Exception as e:
            logger.error(f"Error ingesting CV '{file_path}': {e}", exc_info=True)
        
    # 2. Run matching and ranking for the JD
    logger.info("--- MATCHING AND SCORING CANDIDATES AGAINST JD ---")
    # Using standard technical weights
    weights = ScoringWeights(
        skills=0.45,
        experience=0.35,
        education=0.10,
        culture_fit=0.10
    )
    
    try:
        # We call rank_candidates with the JD PDF file
        results = pipeline.rank_candidates(
            jd_text_or_file=jd_file,
            weights=weights,
            limit=5
        )
        
        # 3. Print the results
        logger.info("=== FINAL MATCHING RESULTS FOR THE JD ===")
        for idx, match in enumerate(results):
            print(f"\n{idx + 1}. Candidate: {match['candidate_name']} (ID: {match['candidate_id']})")
            print(f"   OVERALL MATCH SCORE: {match['score']}%")
            print("   Score Breakdown:")
            print(f"      - Skills:      {match['breakdown']['skills']}/100")
            print(f"      - Experience:  {match['breakdown']['experience']}/100")
            print(f"      - Education:   {match['breakdown']['education']}/100")
            print(f"      - Culture Fit: {match['breakdown']['culture_fit']}/100")
            
            hard = match['hard_match']
            print("   Hard Match Constraints:")
            print(f"      - Experience passed: {'PASS' if hard['exp_passed'] else 'FAIL'} ({hard['relevant_years']} yrs computed, requested {hard['required_years']} yrs)")
            print(f"      - Skills passed:     {'PASS' if hard['skills_passed'] else 'FAIL'}")
            print(f"      - Education passed:  {'PASS' if hard['education_passed'] else 'FAIL'}")
            print(f"      - English Skill:     {'YES' if hard.get('has_english', False) else 'NO'}")
            print(f"      - Practical Tenure:  {hard.get('practical_years', 0.0)} yrs (excluding intern/freelance)")
            print(f"      - Has Worked (Corp): {'YES' if hard.get('has_worked', False) else 'NO (Rejected - Projects/Intern only)'}")
            print(f"      - Overall status:    {'PASSED' if hard['overall_hard_match_passed'] else 'FAILED'}")
            
            print(f"   Key Strengths: {', '.join(match['strengths'])}")
            print(f"   Missing/Weak Skills: {', '.join(match['missing_skills']) or 'None'}")
            print(f"   Reasoning:\n      {match['reasoning']}")
            print("-" * 80)
            
    except Exception as e:
        logger.error(f"Error matching candidates: {e}", exc_info=True)

if __name__ == "__main__":
    main()
