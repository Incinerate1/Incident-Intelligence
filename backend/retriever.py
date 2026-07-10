import json
import os
import logging
import re
from typing import List, Dict, Any
from backend.models import JiraTicketCandidate
from backend.mcp_client import mcp_client, McpConnectionError, McpAtlassianCloudError
from backend.config import settings

logger = logging.getLogger("candidate_retriever")

class CandidateRetriever:
    """
    Candidate Ticket Retrieval Engine via Atlassian MCP (`jira_search_issues`).
    Enforces 400 JQL syntax retry (`EC-1.4`), offline Local KB fallback (`EC-2.1`),
    zero retrieval handling (`EC-2.3`), and verified KB tag detection (`EC-4.2`).
    """
    @classmethod
    def retrieve_candidates(cls, jql: str, alert_trace: str = "") -> List[JiraTicketCandidate]:
        try:
            raw_issues = mcp_client.execute_jira_search(jql, max_results=20)
        except (ValueError, McpConnectionError) as e:
            err_str = str(e).lower()
            if "syntax" in err_str or "400" in err_str or "jql" in err_str:
                logger.warning(f"EC-1.4 JQL Syntax Error caught ({e}). Retrying with simple keyword search...")
                simple_words = [w for w in re.split(r'\s+', alert_trace) if len(w) > 4 and w.isalnum()][:2]
                fallback_jql = f'PROJECT in ("{settings.jira_project_keys[0]}") ORDER BY created DESC'
                if simple_words:
                    fallback_jql = f'PROJECT in ("{settings.jira_project_keys[0]}") AND text ~ "{simple_words[0]}" ORDER BY created DESC'
                try:
                    raw_issues = mcp_client.execute_jira_search(fallback_jql, max_results=20)
                except Exception as e2:
                    logger.warning(f"EC-2.1 Retry failed ({e2}). Switching to Local KB fallback...")
                    return cls._offline_local_fallback(alert_trace or jql)
            else:
                logger.warning(f"EC-2.1 Atlassian MCP unreachable ({e}). Switching to Local KB fallback...")
                return cls._offline_local_fallback(alert_trace or jql)
        except Exception as e:
            logger.warning(f"EC-2.1 Unexpected retrieval error ({e}). Switching to Local KB fallback...")
            return cls._offline_local_fallback(alert_trace or jql)

        # Parse online issues into structured candidates
        candidates = []
        for issue in raw_issues:
            fields = issue.get("fields", {})
            desc = fields.get("description", "") or ""
            comments = [c.get("body", "") for c in fields.get("comment", {}).get("comments", []) if c.get("body")]
            
            # Check for [INCIDENT_INTELLIGENCE_KB_ENTRY] tag (`EC-4.2`)
            has_kb = "[INCIDENT_INTELLIGENCE_KB_ENTRY]" in desc or any("[INCIDENT_INTELLIGENCE_KB_ENTRY]" in c for c in comments)
            
            cand = JiraTicketCandidate(
                issue_key=issue.get("key", f"{settings.jira_project_keys[0]}-000"),
                summary=fields.get("summary", "No summary"),
                description=desc,
                comments=comments,
                created=fields.get("created", ""),
                assignee=fields.get("assignee", {}).get("displayName", "Unassigned") if isinstance(fields.get("assignee"), dict) else "Unassigned",
                has_verified_kb_entry=has_kb
            )
            candidates.append(cand)

        # Merge local store matches (pending sync / local KB entries) with online candidates (`EC-2.3` & `EC-4.2`)
        local_matches = cls._offline_local_fallback(alert_trace or jql)
        existing_keys = {c.issue_key for c in candidates}
        for lm in local_matches:
            if lm.issue_key not in existing_keys:
                candidates.append(lm)

        return candidates

    @classmethod
    def _offline_local_fallback(cls, query_context: str) -> List[JiraTicketCandidate]:
        """
        Reads `data/kb_store.json` to serve verified offline resolutions (`EC-2.1`).
        """
        kb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kb_store.json")
        if not os.path.exists(kb_path):
            return []
            
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read local kb_store.json: {e}")
            return []

        if query_context == "WEEKLY_SUMMARY_ALL_RECENT":
            matched_candidates = []
            for rec in records[:50]:
                matched_candidates.append(JiraTicketCandidate(
                    issue_key=rec.get("kb_id", "CR-KB-101"),
                    summary=f"Resolved: {rec.get('precursor_condition', '')[:60]}",
                    description=rec.get("resolution_narrative", ""),
                    comments=[f"Comment: {rec.get('resolution_narrative', '')}"],
                    created="2026-07-08T00:00:00Z",
                    assignee=rec.get("escalation_owner", "Unassigned"),
                    has_verified_kb_entry=False
                ))
            return matched_candidates

        stopwords = {"error", "exception", "failure", "during", "batch", "node", "server", "system", "issue", "alert", "active", "queue", "thread", "with", "from", "when", "after"}
        raw_terms = [t.lower() for t in re.split(r'\s+|,|\.|\(|\)|\"|\~|\=|\+|\_|\-', query_context) if len(t) > 3]
        query_terms = [t for t in raw_terms if t not in stopwords]
        if not query_terms:
            return []

        matched_candidates = []
        for rec in records:
            sig = rec.get("alert_signature", "").lower()
            desc = rec.get("resolution_narrative", "")
            precursor = rec.get("precursor_condition", "")
            
            # Check exact substring overlap OR strict term overlap count
            exact_match = (sig and sig in query_context.lower()) or (query_context.lower() in sig) or (precursor and precursor.lower() in query_context.lower())
            rec_text = f"{sig} {desc} {precursor}".lower()
            matching_terms = [term for term in query_terms if term in rec_text]
            
            if exact_match or len(matching_terms) >= 2 or (len(query_terms) == 1 and len(matching_terms) == 1 and len(query_terms[0]) >= 6):
                # Only set has_verified_kb_entry=True when exact match or strong overlap (>50% of query terms)
                is_strong_kb_match = exact_match or (len(matching_terms) / max(1, len(query_terms)) >= 0.5)
                has_kb = is_strong_kb_match and ("[INCIDENT_INTELLIGENCE_KB_ENTRY]" in desc or "[INCIDENT_INTELLIGENCE_KB_ENTRY]" in precursor or rec.get("sync_status") in ["SYNCED", "PENDING_JIRA_SYNC"])
                
                cand = JiraTicketCandidate(
                    issue_key=rec.get("kb_id", "CR-KB-101"),
                    summary=f"Resolved: {precursor[:60]}",
                    description=desc,
                    comments=[f"[INCIDENT_INTELLIGENCE_KB_ENTRY] Verified Fix: {desc}" if has_kb else f"Comment: {desc}"],
                    created="2026-07-08T00:00:00Z",
                    assignee=rec.get("escalation_owner", "Unassigned"),
                    has_verified_kb_entry=has_kb
                )
                matched_candidates.append(cand)

        return matched_candidates
