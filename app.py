import os
import sys
import uuid
import json
import logging
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Configure logging
from utils.logger import setup_logger
logger = setup_logger("CVMatcherAPI", log_file="api.log")

# Initialize FastAPI app
app = FastAPI(
    title="RAG CV Matcher API",
    description="Backend API server for candidate CV parsing and Neo-Brutalist Matcher frontend."
)

# Configure CORS for developer ease
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import the pipeline and schemas
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from RAG.pipeline import CVMatcherPipeline
from RAG.schemas import ScoringWeights

# Initialize pipeline as a singleton
try:
    pipeline = CVMatcherPipeline()
except Exception as e:
    logger.error(f"Failed to initialize CVMatcherPipeline: {e}", exc_info=True)
    pipeline = None

def background_ontology_wiring(threshold: int = 10):
    """Background task to run incremental ontology wiring if orphan node thresholds are met."""
    try:
        logger.info(f"Checking for unwired ontology nodes (Threshold: {threshold})...")
        from GRAPHRAG.ontology_wire import OntologyWire
        wire = OntologyWire()
        wire.wire_major_ontology(threshold=threshold)
        wire.wire_jobposition_ontology(threshold=threshold)
        wire.wire_skill_ontology(threshold=threshold)
        wire.wire_skillgroup_skill_ontology(threshold=threshold)
        wire.wire_company_industry_ontology(threshold=threshold)
    except Exception as e:
        logger.error(f"Background ontology wiring failed: {e}")

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "pipeline_active": pipeline is not None,
        "qdrant_active": pipeline.vector_db.real_client is not None if pipeline else False
    }

@app.get("/api/candidates")
def get_candidates():
    if not pipeline:
        raise HTTPException(status_code=503, detail="Matcher pipeline is not initialized")
    try:
        return pipeline.vector_db.list_all_cvs()
    except Exception as e:
        logger.error(f"Error listing candidates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload_cv")
def upload_cv(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not pipeline:
        raise HTTPException(status_code=530, detail="Matcher pipeline is not initialized")
    try:
        # Create uploads folder inside workspace if it doesn't exist
        upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        cv_id = str(uuid.uuid4())
        
        # Save to uploads folder permanently with a unique prefix to avoid collisions
        safe_filename = f"{cv_id}_{file.filename}"
        saved_path = os.path.join(upload_dir, safe_filename)
        
        logger.info(f"Saving uploaded file permanently to {saved_path}")
        with open(saved_path, "wb") as f:
            f.write(file.file.read())
            
        cv_schema = pipeline.ingest_cv(saved_path, cv_id=cv_id)
            
        # Trigger event-driven threshold check in background (Non-blocking)
        background_tasks.add_task(background_ontology_wiring, 10)

        return {
            "status": "success",
            "id": cv_id,
            "candidate": cv_schema.model_dump()
        }
    except Exception as e:
        logger.error(f"Error ingesting uploaded CV: {e}", exc_info=True)
        if 'saved_path' in locals() and os.path.exists(saved_path):
            try:
                os.remove(saved_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/candidates/{id}")
def delete_candidate(id: str):
    if not pipeline:
        raise HTTPException(status_code=503, detail="Matcher pipeline is not initialized")
    try:
        # Get candidate payload first to find physical file path
        cv_payload = pipeline.vector_db.get_cv(id)
        file_path = cv_payload.get("file_path") if cv_payload else None

        success = pipeline.vector_db.delete_cv(id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Candidate with ID '{id}' not found")
            
        # Delete local physical file if it exists
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted local CV file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete local file '{file_path}': {e}")
                
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error deleting candidate '{id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/match")
def match_candidates(
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
    weights: str = Form(...)
):
    if not pipeline:
        raise HTTPException(status_code=503, detail="Matcher pipeline is not initialized")
    try:
        # Parse weights
        weights_dict = json.loads(weights)
        scoring_weights = ScoringWeights(**weights_dict)
        
        # Resolve JD path or content
        temp_path = None
        if jd_file and jd_file.filename:
            temp_dir = os.path.join(os.path.dirname(__file__), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            file_ext = os.path.splitext(jd_file.filename)[1]
            temp_filename = f"jd_{uuid.uuid4().hex}{file_ext}"
            temp_path = os.path.join(temp_dir, temp_filename)
            
            logger.info(f"Saving uploaded JD file temporarily to {temp_path}")
            with open(temp_path, "wb") as f:
                f.write(jd_file.file.read())
            jd_source = temp_path
        elif jd_text:
            jd_source = jd_text
        else:
            raise HTTPException(status_code=400, detail="Must provide either jd_text or jd_file")
            
        logger.info(f"Evaluating candidate matches with weights: {scoring_weights}")
        results = pipeline.rank_candidates(jd_source, weights=scoring_weights, limit=10)
        
        # Cleanup
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            
        return results
    except Exception as e:
        logger.error(f"Error performing candidate matching: {e}", exc_info=True)
        if 'temp_path' in locals() and temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/load_samples")
def load_samples():
    if not pipeline:
        raise HTTPException(status_code=503, detail="Matcher pipeline is not initialized")
    try:
        sample_cvs = [
            ("HoangThaiAnh_AIEngineer.pdf", "11111111-1111-1111-1111-111111111111"),
            ("LeThanhNhanCVTiengViet.pdf", "22222222-2222-2222-2222-222222222222")
        ]
        upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        ingested = []
        import shutil
        for file_name, cv_id in sample_cvs:
            full_path = os.path.join(os.path.dirname(__file__), file_name)
            if os.path.exists(full_path):
                # Copy to uploads permanently with unique name
                unique_filename = f"{cv_id}_{file_name}"
                saved_path = os.path.join(upload_dir, unique_filename)
                
                logger.info(f"Copying sample CV {file_name} to permanent store: {saved_path}")
                shutil.copy2(full_path, saved_path)
                
                cv_schema = pipeline.ingest_cv(saved_path, cv_id=cv_id)
                ingested.append({"id": cv_id, "name": cv_schema.name, "file": file_name})
            else:
                logger.warning(f"Sample CV not found at: {full_path}")
                
        return {
            "status": "success",
            "ingested_count": len(ingested),
            "ingested": ingested
        }
    except Exception as e:
        logger.error(f"Error loading sample CVs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/load_sample_jd")
def load_sample_jd():
    if not pipeline:
        raise HTTPException(status_code=503, detail="Matcher pipeline is not initialized")
    try:
        jd_path = os.path.join(os.path.dirname(__file__), "AI ENGINEER JD.pdf")
        if os.path.exists(jd_path):
            logger.info(f"Extracting sample JD from file: {jd_path}")
            from PARSING.ParsingDocument import parse_document
            text = parse_document(jd_path)
            return {"text": text, "filename": "AI ENGINEER JD.pdf"}
        else:
            logger.warning(f"Sample JD not found at: {jd_path}")
            return {"text": "", "error": "Sample JD file not found in workspace"}
    except Exception as e:
        logger.error(f"Error parsing sample JD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Mount Vite build outputs if they exist, facilitating production service
dist_dir = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")
    logger.info("Mounted static frontend build folder.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
