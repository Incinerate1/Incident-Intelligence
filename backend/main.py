import os
import time
import logging
from fastapi import FastAPI, Request, status, Query
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.models import QueryRequest, ResolutionCaptureRequest, PatternResponse
from backend.jql_translator import ScopedJqlTranslator
from backend.retriever import CandidateRetriever
from backend.semantic_filter import SemanticFilter
from backend.pattern_engine import PatternEngine
from backend.learning_loop import LearningLoopController
from backend.weekly_summary import WeeklySummaryController

logger = logging.getLogger("api_gateway")

app = FastAPI(
    title="Incident Intelligence API Gateway",
    description="Agentic 2am P1 Triage via Atlassian MCP & Groq llama-3.3-70b-versatile (< 15.0s SLA)",
    version="1.0.0"
)

# CORS configuration for UI connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Global Pydantic v2 validation error handler (`EC-5.3`).
    Returns clear, user-facing JSON guidance when required fields or minimum lengths are breached.
    """
    errors = exc.errors()
    formatted_messages = []
    for error in errors:
        loc = " -> ".join(str(l) for l in error.get("loc", []))
        msg = error.get("msg", "Invalid input")
        formatted_messages.append(f"Field '{loc}': {msg}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "VALIDATION_ERROR",
            "message": "Input validation rejected. Please verify query and resolution fields meet length requirements (`EC-5.3`).",
            "details": formatted_messages,
            "error_code": "EC-5.3"
        }
    )

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint verifying Phase 1 foundation status and active project scoping (`EC-1.3`)."""
    return {
        "status": "HEALTHY",
        "service": "Incident Intelligence API Gateway",
        "version": "1.0.0",
        "project_scoping": settings.jira_project_keys,
        "groq_api_configured": bool(settings.groq_api_key),
        "atlassian_cloud_url": settings.atlassian_cloud_url,
        "sla_target": "< 15.0s"
    }

@app.post("/api/v1/triage", response_model=dict)
async def triage_incident(req: QueryRequest):
    """
    Core Triage Pipeline (`Phase 2` & `Phase 3`).
    Executes scoped JQL translation, MCP retrieval, semantic grounding, and pattern synthesis in < 15.0s.
    """
    start_time = time.time()
    logger.info(f"Received triage request (`len={len(req.alert_trace)}` chars)")

    # 1. Scoped JQL Query Translation (`EC-1.1`, `EC-1.3`, `EC-1.4`)
    jql = ScopedJqlTranslator.translate_to_jql(req.alert_trace)

    # 2. Candidate Ticket Retrieval (`EC-2.1` offline fallback, `EC-4.2` KB tag check)
    candidates = CandidateRetriever.retrieve_candidates(jql=jql, alert_trace=req.alert_trace)

    # 3. Semantic Grounding Filter (`EC-1.2` ambiguity check, `EC-3.1`/`EC-3.3` rate limit fallback)
    matches = SemanticFilter.filter_and_ground(alert_trace=req.alert_trace, candidates=candidates)

    # 4. Pattern Engine Synthesis (`EC-4.1` sparse threshold, `EC-4.2` KB boost, `EC-3.2` >50% majority rule)
    pattern_card = PatternEngine.synthesize_pattern(matches)

    elapsed = time.time() - start_time
    logger.info(f"Triage pipeline completed in {elapsed:.2f}s (`status={pattern_card.status}`)")

    return {
        "pattern": pattern_card.model_dump(),
        "meta": {
            "elapsed_seconds": round(elapsed, 3),
            "jql_executed": jql,
            "candidates_retrieved": len(candidates),
            "semantic_matches_count": len(matches)
        }
    }

@app.post("/api/v1/capture-resolution", response_model=dict)
async def capture_resolution(req: ResolutionCaptureRequest):
    """
    Continuous Learning Loop & KB Write-Back Endpoint (`JTBD 2`).
    Enforces concurrent deduplication (`EC-5.1`) and Atlassian read-only dual storage fallback (`EC-5.2`).
    """
    logger.info(f"Received resolution capture (`signature={req.alert_signature[:40]}...`)")
    res = LearningLoopController.capture_and_externalize(req)
    return res

@app.get("/api/v1/weekly-summary", response_model=dict)
async def get_weekly_summary(
    project: str = Query("CR", description="Jira Project Key e.g. CR or CREP"),
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze")
):
    """Shift Manager Weekly Summary Endpoint (`Step 4.3`). Returns Top 3 Recurring Alert Clusters."""
    logger.info(f"Generating weekly summary (`project={project}`, `days={days}`)")
    return WeeklySummaryController.generate_summary(project_key=project, days=days)

# Mount Dark-Mode Web UI static directory at / and /ui
ui_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")
if os.path.exists(ui_path):
    app.mount("/", StaticFiles(directory=ui_path, html=True), name="ui")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
