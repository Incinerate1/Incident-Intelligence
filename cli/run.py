import sys
import time
import argparse
import logging
from rich.console import Console
from rich.status import Status
from backend.models import QueryRequest, ResolutionCaptureRequest
from backend.jql_translator import ScopedJqlTranslator
from backend.retriever import CandidateRetriever
from backend.semantic_filter import SemanticFilter
from backend.pattern_engine import PatternEngine
from backend.learning_loop import LearningLoopController
from backend.weekly_summary import WeeklySummaryController
from cli.formatter import TerminalFormatter, console

# Configure safe UTF-8 output on Windows terminal
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("cli_run")

def execute_triage(alert_trace: str) -> None:
    """Executes full 2am P1 triage pipeline with real-time status spinner (`Step 4.1`)."""
    start_time = time.time()
    
    with console.status("[bold cyan]Translating alert to scoped JQL (`EC-1.3`)...[/bold cyan]") as status:
        jql = ScopedJqlTranslator.translate_to_jql(alert_trace)
        
        status.update("[bold cyan]Searching candidate tickets via Atlassian MCP (`EC-2.1`)...[/bold cyan]")
        candidates = CandidateRetriever.retrieve_candidates(jql=jql, alert_trace=alert_trace)
        
        status.update(f"[bold cyan]Filtering & grounding {len(candidates)} candidates via Groq (`EC-1.2`)...[/bold cyan]")
        matches = SemanticFilter.filter_and_ground(alert_trace=alert_trace, candidates=candidates)
        
        status.update("[bold cyan]Extracting >50% majority-rule pattern (`EC-3.2`)...[/bold cyan]")
        pattern_card = PatternEngine.synthesize_pattern(matches)
        
    elapsed = time.time() - start_time
    TerminalFormatter.render_pattern_card(pattern_card, elapsed=elapsed)

def execute_capture_resolution() -> None:
    """Interactive CLI walkthrough for documenting new Known-Error resolutions (`JTBD 2`)."""
    console.print("\n[bold cyan]📝 Incident Intelligence — Document Known-Error Resolution (`JTBD 2`)[/bold cyan]")
    try:
        alert_signature = console.input("[bold white]1. Enter Alert Signature or Error Header (min 10 chars): [/bold white]").strip()
        precursor_condition = console.input("[bold white]2. Enter Precursor Condition / Root Cause (min 15 chars): [/bold white]").strip()
        resolution_narrative = console.input("[bold white]3. Enter Step-by-Step Resolution Narrative (min 30 chars): [/bold white]").strip()
        escalation_owner = console.input("[bold white]4. Enter Escalation Owner / Team (e.g. reporting-team): [/bold white]").strip() or "Unassigned"
        existing_key = console.input("[bold white]5. Optional existing Jira Issue Key to append comment (or leave blank to create new): [/bold white]").strip() or None

        with console.status("[bold green]Validating schema (`EC-5.3`) & verifying deduplication (`EC-5.1`)...[/bold green]"):
            req = ResolutionCaptureRequest(
                alert_signature=alert_signature,
                precursor_condition=precursor_condition,
                resolution_narrative=resolution_narrative,
                escalation_owner=escalation_owner,
                existing_issue_key=existing_key
            )
            res = LearningLoopController.capture_and_externalize(req)

        console.print()
        if res["status"] == "DUPLICATE_DEDUPLICATED":
            console.print(f"[bold yellow]⚠️ {res['message']}[/bold yellow]\n")
        elif res["status"] == "LOCAL_FALLBACK_SAVED":
            console.print(f"[bold yellow]⚠️ Saved directly to local store (`sync_status=PENDING_JIRA_SYNC`) (`EC-5.2`): {res['message']}[/bold yellow]\n")
        else:
            console.print(f"[bold green]✅ Resolution Documented & Indexed via Atlassian MCP! Record Key: {res['kb_id']}[/bold green]\n")
    except Exception as e:
        console.print(f"\n[bold red]Validation Error (`EC-5.3`): {e}[/bold red]\n")

def execute_weekly_summary(project: str, days: int) -> None:
    """Executes shift manager weekly summary clustering (`Step 4.3`)."""
    with console.status(f"[bold yellow]Analyzing recent incidents over last {days} days for project [{project}]...[/bold yellow]"):
        summary = WeeklySummaryController.generate_summary(project_key=project, days=days)
    TerminalFormatter.render_weekly_summary(summary)

def execute_benchmark(query: str) -> None:
    """End-to-End Latency Benchmarking (`Verification Criteria Phase 4`)."""
    console.print(f"\n[bold cyan]⏱️ Running End-to-End Latency Benchmark for query: `{query}`[/bold cyan]")
    start = time.time()
    execute_triage(query)
    total = time.time() - start
    console.print(f"[bold {'green' if total < 15.0 else 'red'}]🎯 Total Benchmark Wall-Clock Time: {total:.3f} seconds (SLA Target: < 15.0s)[/bold {'green' if total < 15.0 else 'red'}]\n")

def main():
    parser = argparse.ArgumentParser(description="Incident Intelligence — 2am P1 Triage & Resolution CLI")
    parser.add_argument("--query", "-q", type=str, help="Raw alert text or stack trace to triage")
    parser.add_argument("--capture-resolution", "-c", action="store_true", help="Interactive walkthrough to document new resolution")
    parser.add_argument("--weekly-summary", "-w", action="store_true", help="Generate shift lead weekly summary")
    parser.add_argument("--project", "-p", type=str, default="CR", help="Jira project key for summary (default: CR)")
    parser.add_argument("--days", "-d", type=int, default=7, help="Number of days for summary (default: 7)")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Run latency benchmark on --query")

    args = parser.parse_args()

    if args.capture_resolution:
        execute_capture_resolution()
    elif args.weekly_summary:
        execute_weekly_summary(args.project, args.days)
    elif args.query:
        if args.benchmark:
            execute_benchmark(args.query)
        else:
            execute_triage(args.query)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
