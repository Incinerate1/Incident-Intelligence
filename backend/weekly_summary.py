import json
import logging
from typing import Dict, Any, List
from collections import Counter
from backend.mcp_client import mcp_client, McpConnectionError
from backend.retriever import CandidateRetriever
from backend.llm_client import llm_client, GroqRateLimitExceededError, GroqTimeoutError
from backend.prompts.weekly_prompts import WEEKLY_CLUSTER_PROMPT

logger = logging.getLogger("weekly_summary")

class WeeklySummaryController:
    """
    Shift Manager Weekly Summary Engine (`Step 4.3`).
    Fetches recent incidents over N days, clusters semantically into Top 3 alert frequencies,
    and provides deterministic keyword clustering on LLM fallback (`EC-3.1`).
    """
    @classmethod
    def generate_summary(cls, project_key: str = "CR", days: int = 7) -> Dict[str, Any]:
        jql = f'PROJECT in ("{project_key}") AND created >= -{days}d ORDER BY created DESC'
        logger.info(f"Executing weekly summary search with JQL: {jql}")

        # Fetch candidate tickets via CandidateRetriever (automatically handles offline fallback if Atlassian offline)
        candidates = CandidateRetriever.retrieve_candidates(jql=jql, alert_trace="WEEKLY_SUMMARY_ALL_RECENT")
        
        if not candidates:
            return {
                "project_key": project_key,
                "days": days,
                "total_tickets_analyzed": 0,
                "clusters": [],
                "status": "NO_INCIDENTS_FOUND",
                "message": f"No incident tickets found in project {project_key} over the last {days} days."
            }

        # Format candidates for LLM clustering
        ticket_lines = []
        for c in candidates[:50]:
            ticket_lines.append(f"Key: {c.issue_key} | Summary: {c.summary} | Assignee: {c.assignee} | Desc: {c.description[:150]}")
        
        tickets_text = "\n".join(ticket_lines)
        prompt = WEEKLY_CLUSTER_PROMPT.format(days=days, project_key=project_key, tickets_text=tickets_text)

        try:
            raw_json = llm_client.generate(prompt=prompt, timeout_seconds=4.5)
            parsed = cls._parse_json(raw_json)
            if parsed and "clusters" in parsed and isinstance(parsed["clusters"], list):
                top_clusters = parsed["clusters"][:3]
                return {
                    "project_key": project_key,
                    "days": days,
                    "total_tickets_analyzed": len(candidates),
                    "clusters": top_clusters,
                    "status": "SUCCESS",
                    "mode": "LLM_SEMANTIC_CLUSTERING"
                }
        except (GroqRateLimitExceededError, GroqTimeoutError, Exception) as e:
            logger.warning(f"EC-3.1 / EC-3.3 Weekly clustering fallback: {e}. Executing deterministic keyword frequency grouping.")

        # Deterministic Keyword Clustering Fallback (`EC-3.1`/`EC-3.3`)
        return cls._deterministic_clustering(candidates, project_key, days)

    @classmethod
    def _deterministic_clustering(cls, candidates: List[Any], project_key: str, days: int) -> Dict[str, Any]:
        # Group by simple keyword buckets
        buckets: Dict[str, List[Any]] = {
            "Memory / JVM Heap Exhaustion": [],
            "Database / SQL Connection Issues": [],
            "Network / Service Timeout Alerts": [],
            "General System Errors": []
        }

        for c in candidates:
            text = f"{c.summary} {c.description}".lower()
            if any(k in text for k in ["memory", "heap", "jvm", "outofmemory", "exhausted"]):
                buckets["Memory / JVM Heap Exhaustion"].append(c)
            elif any(k in text for k in ["sql", "db", "database", "query", "pool"]):
                buckets["Database / SQL Connection Issues"].append(c)
            elif any(k in text for k in ["timeout", "gateway", "network", "latency", "connection"]):
                buckets["Network / Service Timeout Alerts"].append(c)
            else:
                buckets["General System Errors"].append(c)

        # Sort buckets by frequency
        sorted_buckets = sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)
        clusters = []
        for title, t_list in sorted_buckets[:3]:
            if not t_list:
                continue
            assignees = list(set(c.assignee for c in t_list if c.assignee != "Unassigned")) or ["Unassigned"]
            clusters.append({
                "cluster_title": title,
                "frequency_count": len(t_list),
                "dominant_root_cause": f"Recurring {title.lower()} triggers in production environment",
                "affected_assignees": assignees,
                "sample_tickets": [c.issue_key for c in t_list[:3]]
            })

        return {
            "project_key": project_key,
            "days": days,
            "total_tickets_analyzed": len(candidates),
            "clusters": clusters,
            "status": "SUCCESS",
            "mode": "DETERMINISTIC_FREQUENCY_FALLBACK (`EC-3.1`/`EC-3.3`)"
        }

    @staticmethod
    def _parse_json(text: str) -> dict:
        if not text:
            return {}
        try:
            return json.loads(text.strip())
        except Exception:
            import re
            match = re.search(r'\{[^{}]*\}', text)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return {}
