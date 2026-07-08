from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

class QueryRequest(BaseModel):
    """Input request model for triage queries (`EC-1.2`)."""
    alert_trace: str = Field(..., min_length=10, description="Raw alert text or stack trace from engineer")
    project_override: Optional[str] = Field(None, description="Optional project key override")

    @field_validator("alert_trace")
    @classmethod
    def check_min_length(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("EC-1.2 Query Ambiguity: alert_trace must be at least 10 characters long.")
        return v

class JiraTicketCandidate(BaseModel):
    """Structured representation of a Jira issue candidate retrieved from Atlassian MCP (`retriever.py`)."""
    issue_key: str = Field(..., description="Jira issue key e.g. CR-101")
    summary: str = Field(..., description="Issue title or summary")
    description: str = Field("", description="Detailed issue description")
    comments: List[str] = Field(default_factory=list, description="List of issue comments")
    created: str = Field("", description="Creation timestamp ISO string")
    assignee: str = Field("Unassigned", description="Assigned engineer username/ID")
    has_verified_kb_entry: bool = Field(False, description="True if [INCIDENT_INTELLIGENCE_KB_ENTRY] tag detected (EC-4.2)")

class SemanticMatchResult(BaseModel):
    """Result of semantic similarity grounding evaluation (`semantic_filter.py`)."""
    candidate: JiraTicketCandidate
    is_semantic_match: bool = Field(..., description="True if LLM or fallback verified root-cause alignment")
    confidence_score: float = Field(0.0, ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0")
    reasoning: str = Field("", description="Explanation of match or non-match")

class KnowledgeBaseEntry(BaseModel):
    """Structured Known-Error KB record (`data/kb_store.json`)."""
    kb_id: str
    alert_signature: str
    precursor_condition: str
    resolution_narrative: str
    escalation_owner: str
    created_timestamp: float
    sync_status: str = "SYNCED" # or PENDING_JIRA_SYNC (`EC-5.2`)
    content_hash: Optional[str] = None # SHA-256 for deduplication (`EC-5.1`)

class ResolutionCaptureRequest(BaseModel):
    """
    Schema for documenting new Known-Error resolutions (`JTBD 2`).
    Enforces minimum length guardrails (`EC-5.3`) to prevent blank/vague resolution pollution.
    """
    alert_signature: str = Field(..., min_length=10, description="Core exception signature or error header")
    precursor_condition: str = Field(..., min_length=15, description="Root cause or environmental trigger condition")
    resolution_narrative: str = Field(..., min_length=30, description="Step-by-step resolution narrative")
    escalation_owner: str = Field("Unassigned", description="Owning team or shift lead responsible for issue")
    existing_issue_key: Optional[str] = Field(None, description="Optional existing Jira ticket key to append fix comment (`EC-5.2`)")

    @field_validator("precursor_condition")
    @classmethod
    def check_precursor_length(cls, v: str) -> str:
        if len(v.strip()) < 15:
            raise ValueError("EC-5.3 Validation Error: precursor_condition must be at least 15 characters describing the root cause.")
        return v

    @field_validator("resolution_narrative")
    @classmethod
    def check_resolution_length(cls, v: str) -> str:
        if len(v.strip()) < 30:
            raise ValueError("EC-5.3 Validation Error: resolution_narrative must be at least 30 characters detailing the fix steps.")
        return v

class PatternResponse(BaseModel):
    """Structured pattern synthesis card returned to UI/CLI (`pattern_engine.py`)."""
    status: str = Field(..., description="HIGH_CONFIDENCE_PATTERN, VERIFIED_KB_RESOLUTION, LOW_CONFIDENCE_SPARSE, or NO_MATCHES_FOUND")
    precursor_condition: str = Field("Unverified (Sparse historical data)", description="Dominant precursor condition (`>50%` majority check)")
    escalation_owner: str = Field("Unverified (Requires manual triage)", description="Primary escalation target")
    pattern_count: int = Field(0, description="Number of verified historical matches")
    date_range: str = Field("N/A", description="Temporal recurrence range string e.g. Jan 12, 2026 - Jul 02, 2026")
    summary_stats: str = Field("", description="Formatted recurrence string e.g. 11 times in 6 months")
    matched_tickets: List[str] = Field(default_factory=list, description="Clickable ticket URLs e.g. browse/CR-101")
    resolution_steps: Optional[str] = Field(None, description="Exact step-by-step resolution if verified KB entry exists")
    warning_message: Optional[str] = Field(None, description="Warning banner for low confidence, varied consensus (`EC-3.2`), or offline mode")
