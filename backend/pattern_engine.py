import json
import logging
from typing import List
from backend.models import SemanticMatchResult, PatternResponse, JiraTicketCandidate
from backend.stats_calculator import StatsCalculator
from backend.prompts.pattern_prompts import MAJORITY_PATTERN_EXTRACTION_PROMPT
from backend.llm_client import llm_client, GroqRateLimitExceededError, GroqTimeoutError

logger = logging.getLogger("pattern_engine")

class PatternEngine:
    """
    Majority-Rule Pattern Synthesis Engine (`Step 3.1`).
    Enforces sparse thresholds (`EC-4.1`), verified KB priority override (`EC-4.2`),
    zero match handling (`EC-4.3`), and >50% majority-rule consensus (`EC-3.2`).
    """
    @classmethod
    def synthesize_pattern(cls, matches: List[SemanticMatchResult]) -> PatternResponse:
        # Filter strictly for positive semantic matches (`is_semantic_match == True` or high confidence)
        verified = [m for m in matches if m.is_semantic_match or m.confidence_score >= 0.55]
        count = len(verified)

        # 1. Zero Match Check (`EC-4.3`)
        if count == 0:
            return PatternResponse(
                status="NO_MATCHES_FOUND",
                precursor_condition="No matching precursor found",
                escalation_owner="N/A",
                pattern_count=0,
                date_range="N/A",
                summary_stats="0 matches",
                matched_tickets=[],
                warning_message="No matching historical tickets found for this alert signature (`EC-4.3`)."
            )

        candidates = [m.candidate for m in verified]
        stats = StatsCalculator.calculate_stats(candidates)
        ticket_urls = [f"browse/{c.issue_key}" for c in candidates]

        # 2. Verified KB Priority Override (`EC-4.2`) - overrides sparse checks
        kb_match = next((c for c in candidates if c.has_verified_kb_entry or "[INCIDENT_INTELLIGENCE_KB_ENTRY]" in c.description or any("[INCIDENT_INTELLIGENCE_KB_ENTRY]" in com for com in c.comments)), None)
        if kb_match:
            # Extract resolution steps from KB entry tag
            steps = kb_match.description
            if "[INCIDENT_INTELLIGENCE_KB_ENTRY]" in steps:
                steps = steps.split("[INCIDENT_INTELLIGENCE_KB_ENTRY]")[-1].strip()
            else:
                for com in kb_match.comments:
                    if "[INCIDENT_INTELLIGENCE_KB_ENTRY]" in com:
                        steps = com.split("[INCIDENT_INTELLIGENCE_KB_ENTRY]")[-1].strip()
                        break
            return PatternResponse(
                status="VERIFIED_KB_RESOLUTION",
                precursor_condition=kb_match.summary.replace("Resolved: ", ""),
                escalation_owner=kb_match.assignee,
                pattern_count=stats["pattern_count"],
                date_range=stats["date_range"],
                summary_stats=stats["summary_stats"],
                matched_tickets=ticket_urls,
                resolution_steps=steps,
                warning_message=None
            )

        # 3. Sparse Threshold Check (`EC-4.1` for 1 or 2 matches without verified KB)
        if count in [1, 2]:
            return PatternResponse(
                status="LOW_CONFIDENCE_SPARSE",
                precursor_condition="Unverified (Sparse historical data)",
                escalation_owner="Unverified (Requires manual triage)",
                pattern_count=count,
                date_range=stats["date_range"],
                summary_stats=stats["summary_stats"],
                matched_tickets=ticket_urls,
                warning_message=f"⚠️ Low Confidence: Only {count} historical match(es) found. This does not yet establish a verified recurring pattern (`EC-4.1`)."
            )

        # 4. Majority-Rule Pattern Synthesis (`EC-3.2` for >= 3 matches)
        history_blocks = []
        for c in candidates:
            com_block = "\n".join([f"  - {com[:150]}" for com in c.comments[:2]])
            history_blocks.append(f"Ticket {c.issue_key} | Summary: {c.summary} | Assignee: {c.assignee} | Desc: {c.description[:300]}\nComments:\n{com_block}")
        
        histories_str = "\n---\n".join(history_blocks)
        prompt = MAJORITY_PATTERN_EXTRACTION_PROMPT.format(ticket_histories=histories_str)

        try:
            raw_json = llm_client.generate(prompt=prompt, timeout_seconds=4.0)
            parsed = cls._parse_json(raw_json)
            if parsed:
                precursor = parsed.get("precursor_condition", "Recurring exception under load")
                owner = parsed.get("escalation_owner", candidates[0].assignee)
                has_consensus = parsed.get("has_majority_consensus", True)

                # Check varied triggers warning (`EC-3.2`)
                if not has_consensus or "varied triggers" in precursor.lower() or "no single dominant" in precursor.lower():
                    return PatternResponse(
                        status="HIGH_CONFIDENCE_PATTERN",
                        precursor_condition="No single dominant precursor condition across matches (varied triggers).",
                        escalation_owner=owner,
                        pattern_count=count,
                        date_range=stats["date_range"],
                        summary_stats=stats["summary_stats"],
                        matched_tickets=ticket_urls,
                        warning_message="Historical tickets share exact keywords but stem from conflicting trigger conditions without a clear >50% consensus (`EC-3.2`)."
                    )

                return PatternResponse(
                    status="HIGH_CONFIDENCE_PATTERN",
                    precursor_condition=precursor,
                    escalation_owner=owner,
                    pattern_count=count,
                    date_range=stats["date_range"],
                    summary_stats=stats["summary_stats"],
                    matched_tickets=ticket_urls,
                    warning_message=None
                )
        except (GroqRateLimitExceededError, GroqTimeoutError, Exception) as e:
            logger.warning(f"EC-3.1 / EC-3.3 Pattern synthesis fallback: {e}")

        # Deterministic Majority Fallback (`EC-3.1`/`EC-3.3`)
        from collections import Counter
        owners = Counter([c.assignee for c in candidates if c.assignee != "Unassigned"])
        dom_owner = owners.most_common(1)[0][0] if owners else candidates[0].assignee
        
        return PatternResponse(
            status="HIGH_CONFIDENCE_PATTERN",
            precursor_condition=f"Recurring system error across {count} verified incident tickets",
            escalation_owner=dom_owner,
            pattern_count=count,
            date_range=stats["date_range"],
            summary_stats=stats["summary_stats"],
            matched_tickets=ticket_urls,
            warning_message="Pattern extracted via deterministic frequency fallback (`EC-3.1`/`EC-3.3`)."
        )

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
