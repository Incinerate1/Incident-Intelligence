import logging
import re
import json
from typing import List, Dict, Any, Optional
from backend.models import JiraTicketCandidate, SemanticMatchResult
from backend.llm_client import llm_client, GroqRateLimitExceededError, GroqTimeoutError

logger = logging.getLogger("semantic_filter")

class SemanticFilter:
    """
    Semantic Similarity Grounding Engine (`llama-3.3-70b-versatile`).
    Enforces candidate truncation (`EC-1.1`), ambiguity noise rejection (`EC-1.2`),
    verified KB priority boost (`EC-4.2`), and deterministic keyword overlap fallback (`EC-3.1`/`EC-3.3`).
    """
    @classmethod
    def filter_and_ground(cls, alert_trace: str, candidates: List[JiraTicketCandidate]) -> List[SemanticMatchResult]:
        if not candidates:
            return []

        clean_trace = alert_trace.strip()
        is_generic_short = len(clean_trace) < 25 # (`EC-1.2`)
        results: List[SemanticMatchResult] = []

        for cand in candidates:
            trunc_desc = cand.description[:500] if cand.description else ""
            top_comments = cand.comments[:3] if cand.comments else []
            comment_text = " | ".join([c[:200] for c in top_comments])
            cand_text = f"{cand.summary} {trunc_desc} {comment_text}".lower()

            # Check Verified KB priority override (`EC-4.2`) ONLY IF trace keywords overlap with candidate text
            has_tag = cand.has_verified_kb_entry or "[INCIDENT_INTELLIGENCE_KB_ENTRY]" in cand.description or any("[INCIDENT_INTELLIGENCE_KB_ENTRY]" in c for c in cand.comments)
            stop_words = {'cluster', 'service', 'system', 'server', 'active', 'queue', 'connection', 'timeout', 'exception', 'error', 'thread', 'node', 'manager', 'database', 'application', 'isolated', 'sector'}
            query_words = [w.lower() for w in re.split(r'[^a-zA-Z0-9]+', clean_trace) if len(w) > 4 and w.lower() not in stop_words] or [clean_trace.lower()]
            if has_tag and any(qw in cand_text for qw in query_words):
                results.append(SemanticMatchResult(
                    candidate=cand,
                    is_semantic_match=True,
                    confidence_score=1.0,
                    reasoning="Verified Known-Error KB resolution tag match (`EC-4.2` priority boost)."
                ))
                continue

            # Ambiguity Noise Check (`EC-1.2`)
            if is_generic_short:
                words = [w.lower() for w in re.split(r'\s+', clean_trace) if len(w) > 3]
                cand_text = f"{cand.summary} {trunc_desc} {comment_text}".lower()
                matches = sum(1 for w in words if w in cand_text)
                if matches == 0 or (len(words) > 0 and matches / len(words) < 0.5):
                    results.append(SemanticMatchResult(
                        candidate=cand,
                        is_semantic_match=False,
                        confidence_score=0.20,
                        reasoning="EC-1.2 Ambiguity check: Vague/short query lacks specific root-cause alignment with candidate."
                    ))
                    continue

            # Pre-filter: compute deterministic keyword overlap first (`EC-1.2` / `EC-3.1`)
            overlap_res = cls._deterministic_keyword_match(clean_trace, cand, trunc_desc, comment_text)
            if overlap_res.confidence_score < 0.25:
                results.append(SemanticMatchResult(
                    candidate=cand,
                    is_semantic_match=False,
                    confidence_score=overlap_res.confidence_score,
                    reasoning=f"EC-1.2 Pre-filter rejection: candidate has insufficient term overlap ({overlap_res.confidence_score}) with alert trace."
                ))
                continue

            # Attempt LLM Grounding via Groq
            prompt = f"""
Evaluate if this candidate Jira ticket is a true semantic root-cause match for the incoming error alert.
Incoming Alert: {clean_trace[:800]}
---
Candidate Key: {cand.issue_key}
Candidate Summary: {cand.summary}
Candidate Truncated Description: {trunc_desc}
Candidate Top Comments: {comment_text}
---
Return ONLY a valid JSON object strictly matching this format:
{{"is_match": true, "confidence_score": 0.88, "reasoning": "brief explanation"}}
"""
            try:
                raw_json = llm_client.generate(prompt=prompt, timeout_seconds=3.5)
                # Parse JSON
                parsed = cls._extract_json_from_output(raw_json)
                if parsed and "confidence_score" in parsed:
                    score = float(parsed.get("confidence_score", 0.0))
                    is_match = bool(parsed.get("is_match", score >= 0.55))
                    results.append(SemanticMatchResult(
                        candidate=cand,
                        is_semantic_match=is_match,
                        confidence_score=score,
                        reasoning=str(parsed.get("reasoning", "LLM verified alignment"))
                    ))
                    continue
            except (GroqRateLimitExceededError, GroqTimeoutError, Exception) as e:
                logger.warning(f"EC-3.1 / EC-3.3 Semantic grounding fallback for {cand.issue_key}: {e}. Executing deterministic keyword overlap check.")

            # Deterministic Keyword Fallback (`EC-3.1`, `EC-3.3`)
            fallback_res = cls._deterministic_keyword_match(clean_trace, cand, trunc_desc, comment_text)
            results.append(fallback_res)

        # Filter for verified/high score and sort descending
        matched = [r for r in results if r.is_semantic_match or r.confidence_score >= 0.55]
        matched.sort(key=lambda r: r.confidence_score, reverse=True)
        return matched

    @classmethod
    def _deterministic_keyword_match(cls, alert_trace: str, cand: JiraTicketCandidate, trunc_desc: str, comment_text: str) -> SemanticMatchResult:
        """
        Deterministic Keyword Overlap Fallback (`EC-3.1`/`EC-3.3`).
        Computes exact token overlap without calling external LLM APIs.
        """
        stop_words = {'cluster', 'service', 'system', 'server', 'active', 'queue', 'connection', 'timeout', 'exception', 'error', 'thread', 'node', 'manager', 'database', 'application', 'isolated', 'sector'}
        trace_words = set(w.lower() for w in re.split(r'\s+|,|\.|\(|\)|\"|\~|\=|\+|_', alert_trace) if len(w) > 4 and w.lower() not in stop_words)
        if not trace_words:
            return SemanticMatchResult(
                candidate=cand,
                is_semantic_match=False,
                confidence_score=0.0,
                reasoning="Empty keyword set for fallback comparison."
            )

        cand_text = f"{cand.summary} {trunc_desc} {comment_text}".lower()
        matched_words = [w for w in trace_words if w in cand_text]
        overlap_score = min(1.0, len(matched_words) / max(1, len(trace_words)) * 1.2)
        is_match = overlap_score >= 0.50

        return SemanticMatchResult(
            candidate=cand,
            is_semantic_match=is_match,
            confidence_score=round(overlap_score, 2),
            reasoning=f"Evaluated via deterministic keyword overlap fallback (`EC-3.1`/`EC-3.3`). Matched terms: {matched_words}"
        )

    @staticmethod
    def _extract_json_from_output(text: str) -> Optional[Dict[str, Any]]:
        """Safely extracts JSON dict from LLM response."""
        if not text:
            return None
        try:
            # Try parsing directly
            return json.loads(text.strip())
        except Exception:
            # Find JSON block inside markdown or text
            match = re.search(r'\{[^{}]*\}', text)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return None
        return None
