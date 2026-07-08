import sys
from typing import Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.style import Style
from backend.models import PatternResponse

# Configure safe UTF-8 output on Windows terminal
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

console = Console(legacy_windows=False)

class TerminalFormatter:
    """
    Sleek colorized terminal output renderer (`Step 4.1`).
    Surfaces explicit offline/fallback/sparse badges (`EC-2.1`, `EC-3.1`, `EC-4.1`).
    """
    @classmethod
    def render_pattern_card(cls, card: PatternResponse, elapsed: float = 0.0) -> None:
        console.print()
        
        # Color mapping for card status
        status_colors = {
            "VERIFIED_KB_RESOLUTION": "bold green",
            "HIGH_CONFIDENCE_PATTERN": "bold cyan",
            "LOW_CONFIDENCE_SPARSE": "bold yellow",
            "NO_MATCHES_FOUND": "bold red"
        }
        color = status_colors.get(card.status, "white")

        body = Text()
        
        # Warning/Fallback Banner (`EC-2.1`, `EC-3.1`, `EC-4.1`)
        if card.warning_message:
            body.append("⚠️ WARNING & FALLBACK STATUS:\n", style="bold yellow")
            body.append(f"  {card.warning_message}\n\n", style="yellow")

        body.append("📌 Confidence Status: ", style="bold white")
        body.append(f"{card.status}\n", style=color)
        body.append("🔍 Precursor Condition: ", style="bold white")
        body.append(f"{card.precursor_condition}\n", style="white")
        body.append("👤 Escalation Owner:    ", style="bold white")
        body.append(f"{card.escalation_owner}\n", style="magenta")
        body.append("📊 Temporal Recurrence: ", style="bold white")
        body.append(f"{card.summary_stats} ({card.date_range})\n", style="cyan")

        if card.matched_tickets:
            body.append("\n🔗 Clickable Candidate Tickets:\n", style="bold white")
            for t in card.matched_tickets:
                body.append(f"  • {t}\n", style="blue underline")

        if card.resolution_steps:
            body.append("\n🛠️ Verified Known-Error Resolution (`EC-4.2`):\n", style="bold green")
            body.append(f"{card.resolution_steps}\n", style="green")

        subtitle = f"[dim]SLA Latency: {elapsed:.3f}s (Target: < 15.0s)[/dim]" if elapsed > 0 else "[dim]Incident Intelligence[/dim]"
        panel = Panel(body, title="[bold cyan]⚡ Incident Intelligence Triage Card[/bold cyan]", subtitle=subtitle, border_style="cyan", padding=(1, 2))
        console.print(panel)
        console.print()

    @classmethod
    def render_weekly_summary(cls, summary: Dict[str, Any]) -> None:
        console.print()
        proj = summary.get("project_key", "CR")
        days = summary.get("days", 7)
        mode = summary.get("mode", "ONLINE")

        table = Table(title=f"📅 Shift Manager Weekly Summary — Project [{proj}] (Last {days} Days)", header_style="bold cyan")
        table.add_column("Rank", style="bold white", width=6)
        table.add_column("Cluster Title", style="bold yellow", width=26)
        table.add_column("Frequency", justify="center", style="bold green", width=10)
        table.add_column("Dominant Root Cause / Assignees", style="white")
        table.add_column("Sample Tickets", style="blue")

        for idx, cluster in enumerate(summary.get("clusters", [])):
            assignees = ", ".join(cluster.get("affected_assignees", []))
            samples = ", ".join(cluster.get("sample_tickets", []))
            desc = f"{cluster.get('dominant_root_cause', '')}\n[dim]Assignees: {assignees}[/dim]"
            table.add_row(f"#{idx + 1}", cluster.get("cluster_title", ""), str(cluster.get("frequency_count", 0)), desc, samples)

        console.print(table)
        console.print(f"[dim]Total Tickets Analyzed: {summary.get('total_tickets_analyzed', 0)} | Mode: {mode}[/dim]\n")
