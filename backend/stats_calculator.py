from datetime import datetime
from typing import List, Dict, Any
from backend.models import JiraTicketCandidate

class StatsCalculator:
    """
    Temporal Recurrence & Stats Calculation Engine (`Step 3.2`).
    Computes date ranges and recurrence velocity across verified matches in < 50ms.
    """
    @classmethod
    def calculate_stats(cls, candidates: List[JiraTicketCandidate]) -> Dict[str, Any]:
        count = len(candidates)
        if count == 0:
            return {
                "pattern_count": 0,
                "date_range": "N/A",
                "summary_stats": "0 historical occurrences"
            }

        dates = []
        for cand in candidates:
            if not cand.created:
                continue
            try:
                # Handle ISO timestamps or standard date strings
                clean_dt = cand.created.split("+")[0].replace("Z", "")
                if "T" in clean_dt:
                    dt = datetime.strptime(clean_dt.split(".")[0], "%Y-%m-%dT%H:%M:%S")
                else:
                    dt = datetime.strptime(clean_dt[:10], "%Y-%m-%d")
                dates.append(dt)
            except Exception:
                continue

        if not dates:
            return {
                "pattern_count": count,
                "date_range": "Recent historical tickets",
                "summary_stats": f"{count} times across historical logs"
            }

        dates.sort()
        earliest = dates[0]
        latest = dates[-1]

        earliest_str = earliest.strftime("%b %d, %Y")
        latest_str = latest.strftime("%b %d, %Y")

        if earliest_str == latest_str:
            date_range_str = earliest_str
        else:
            date_range_str = f"{earliest_str} – {latest_str}"

        # Calculate time span delta
        delta_days = max(1, (latest - earliest).days)
        if delta_days >= 30:
            months = max(1, round(delta_days / 30.4))
            summary_str = f"{count} times in {months} month{'s' if months > 1 else ''}"
        elif delta_days > 1:
            summary_str = f"{count} times in {delta_days} days"
        else:
            summary_str = f"{count} times in 24 hours"

        return {
            "pattern_count": count,
            "date_range": date_range_str,
            "summary_stats": summary_str
        }
