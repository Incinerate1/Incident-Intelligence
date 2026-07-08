# Project 1: Incident Intelligence
**An AI-Powered Pattern Recognition & Incident Triage Assistant via Atlassian MCP & Groq (`llama-3.3-70b-versatile`)**

---

## 1. Problem Statement

Production support teams at investment banks handle **50–200+ incidents per month**. Post-mortem data and critical resolutions live scattered across email threads, Jira queues, and Confluence pages that nobody reads or can easily search during an active 2am outage. 

When a high-severity P1 alert triggers at 2am (e.g., during overnight client statement generation or reconciliation runs), frontline L1/L2 engineers face the **"2am P1 Triage Crisis."** They waste **30–60 minutes** manually searching across noisy Slack channels and Jira queues asking: *"Have we seen this alert before? What caused it right before it triggered? Who resolved it, and what is the exact Jira ticket?"*

Because pattern recognition across teams is entirely manual and tribal—trapped inside the minds of senior engineers or buried in unindexed chat histories—the exact same failures recur repeatedly. There is currently no product that surfaces instant, grounded pattern intelligence such as:

> *"This alert has triggered 11 times in the last 6 months (Jan 12, 2026 – Jul 02, 2026)—always preceded by `MemoryPoolExhaustedException` on node `app-client-rep-04` during the `stmt_gen_eod` batch job, always resolved by increasing heap limits, and primarily escalated by L2 Client Reporting Shift Lead @Sarah Jenkins or Node Infra Ops."*

Without this intelligence, **every recurring incident feels like the very first one**, costing teams hundreds of wasted hours in redundant triage and prolonging Mean Time to Resolution (MTTR).

> [!IMPORTANT]
> **The Cost of Tribal Knowledge vs. Agentic Pattern Intelligence**
> When knowledge is siloed, L1/L2 engineers spend **30–60 minutes** guessing or searching manually before spending only **5–15 minutes** applying the actual fix. **Incident Intelligence (v1)** reverses this dynamic by leveraging an agentic workflow over the **Atlassian MCP Server (`jira_search_issues`)** and **Groq Cloud (`llama-3.3-70b-versatile`)**. Within **10–15 seconds**, the agent translates the alert into a scoped JQL search, filters out keyword-only false positives via real ticket text evaluation, extracts verified precursor conditions and escalation owners using strict **>50% majority-rule checks**, and delivers clickable Jira ticket links.

---

## 2. Domain & Target Users

### Domain
**FinTech / Enterprise Ops & Production Tooling** — specifically tailored to investment banking production environments where strict compliance, high alert volume, and complex legacy data flows intersect (e.g., Client Reporting, Statement Generation (`stmt_gen_eod`), and Reconciliation Systems).

### Target Users

| User Segment | Role & Responsibility | Why They Are Targeted |
| :--- | :--- | :--- |
| **Primary** | **L1/L2 Production Support Engineers** | L1/L2 engineers paged at 2am when critical batch jobs fail. They need immediate, verified historical context (`< 10–15s`) to diagnose root causes, apply proven fixes, or escalate accurately to the exact shift lead without guessing. |
| **Secondary** | **Team Leads / Shift Managers** | Responsible for shift handovers, weekly incident review meetings, and identifying recurring operational risks (`Weekly Summary Mode`) to prioritize systemic code fixes over constant firefighting. |
| **Out of Scope** | **VPs & Senior Management** | Executive leadership consumes high-level aggregate MTTR and SLA reporting metrics rather than interacting with real-time diagnostic and troubleshooting workflows. |

---

## 3. Core Jobs To Be Done (JTBD)

```
       [ P1 Alert Fires at 2am ]
                   │
                   ▼
  ┌─────────────────────────────────┐
  │   1. Immediate Pattern Lookup   │
  │  "Have we seen this exact alert │
  │   so I can escalate/fix fast?"  │
  └─────────────────────────────────┘
                   │
                   ▼
  ┌─────────────────────────────────┐
  │  2. Continuous Learning Loop    │
  │  "Can I document this new fix   │
  │   directly via Atlassian MCP?"  │
  └─────────────────────────────────┘
                   │
                   ▼
  ┌─────────────────────────────────┐
  │   3. Weekly Systemic Review     │
  │  "Which recurring alerts need   │
  │   permanent code fixes?"        │
  └─────────────────────────────────┘
```

### 🎯 JTBD 1: Real-Time Pattern Lookup & Confident Escalation (`2am Outage Response`)
> *"When a P1 alert fires at 2am, I need to paste the raw stack trace or alert string into a CLI or dark-mode UI and receive verified recurrence statistics, dominant precursor conditions (`>50% majority rule`), escalation owners, and direct clickable Jira links within **10–15 seconds**, so I can escalate or resolve with confidence."*

### 🎯 JTBD 2: Continuous Learning Loop & Resolution Externalization (`Post-Resolution KB Write-Back`)
> *"When I investigate and resolve a novel or low-confidence incident (`< 3 matches`), I need a 1-click modal to document the exact fix steps and precursor condition back into Jira via **Atlassian MCP (`jira_add_comment` / `jira_create_issue`)** and local index (`data/kb_store.json`), so that on any subsequent occurrence, the agent instantly prioritizes this verified resolution (`VERIFIED_KB_RESOLUTION`) for the team."*

### 🎯 JTBD 3: Shift Management & Weekly Systemic Review (`Weekly Summary Mode`)
> *"When I review my team's weekly incident load as a shift lead, I need an automated summary clustering tickets from the last 7 days (`created >= -7d AND project in ("CREP")`) into dominant failure buckets via `llama-3.3-70b-versatile`, so I can see the **Top 3 Recurring Alerts** and prioritize permanent code fixes over perpetual firefighting."*

---

## 4. Project Deliverables Breakdown

| # | Deliverable | Key Contents & Architectural Mechanics | Target Path / Artifact |
| :---: | :--- | :--- | :--- |
| **1** | **Backend Gateway & LLM Processing Engine** | • **FastAPI Gateway (`backend/main.py`):** Asynchronous REST endpoints (`/api/v1/query`, `/api/v1/capture-resolution`, `/api/v1/weekly-summary`) with strict `Pydantic v2` schema validation (`backend/models.py`).<br>• **Groq Wrapper (`backend/llm_client.py`):** Encapsulates `llama-3.3-70b-versatile`, strict token budgeting, and an `LRUCache` (`15-min TTL`) ensuring compliance with free-tier rate limits (`30 RPM / 12,000 TPM`).<br>• **Atlassian MCP Bridge (`backend/mcp_client.py`):** Protocol wrapper over `mcpservers.org` for `jira_search_issues`, `jira_add_comment`, and `jira_create_issue`. | `backend/main.py`<br>`backend/llm_client.py`<br>`backend/mcp_client.py` |
| **2** | **Scoped Retrieval & Grounding Pipeline** | • **JQL Translator (`backend/jql_translator.py`):** Enforces mandatory query scoping (`PROJECT in ("CREP") AND ... ORDER BY created DESC`) to prevent global search leaks.<br>• **Candidate Retriever (`backend/retriever.py`):** Ingests top 15–25 ticket payloads (`summary`, `description`, `comments`, `created`, `assignee`).<br>• **Semantic Filter (`backend/semantic_filter.py`):** Evaluates true semantic similarity and assigns confidence scores (`0.0–1.0`), eliminating keyword-only false positives. | `backend/jql_translator.py`<br>`backend/retriever.py`<br>`backend/semantic_filter.py` |
| **3** | **Pattern Engine & Continuous Learning Loop** | • **Pattern Engine (`backend/pattern_engine.py`):** Enforces `< 3 matches` sparse warning vs `>= 3 matches` (`>50%` majority rule checks for precursors/owners).<br>• **Stats Calculator (`backend/stats_calculator.py`):** Computes exact date spans and recurrence counts.<br>• **Learning Loop (`backend/kb_writer.py` / `learning_loop.py`):** Writes `[INCIDENT_INTELLIGENCE_KB_ENTRY]` blocks to Jira via MCP and syncs with `data/kb_store.json` for instant priority boosting (`VERIFIED_KB_RESOLUTION`). | `backend/pattern_engine.py`<br>`backend/stats_calculator.py`<br>`backend/kb_writer.py`<br>`data/kb_store.json` |
| **4** | **Interactive CLI & Minimal Chat Web UI** | • **Interactive CLI (`cli/run.py`):** Terminal client (`rich`/`colorama`) with live pipeline spinners, colorized output box, `--capture-resolution`, and `--weekly-summary` flags.<br>• **Dark-Mode Web UI (`ui/index.html` / `ui/app.js`):** Lightweight triage interface featuring scannable badge cards, clickable Jira URLs, and a 1-click **"📝 Document New Resolution"** modal submitting to `/api/v1/capture-resolution`. | `cli/run.py`<br>`ui/index.html`<br>`ui/style.css`<br>`ui/app.js` |
| **5** | **Architecture & Engineering Documentation** | • **Architecture Plan (`ArchitecturePlan.md`):** Complete phase-mapped architectural blueprint, modular data flows, `Pydantic v2` API schemas, latency/token budgets, and verification suites.<br>• **Product Documents (`docs/`):** Discovery document, PRD (`V1 scope & guardrails`), competitive teardown (`PagerDuty/Squadcast`), and historical SQL pattern analysis. | `ArchitecturePlan.md`<br>`Architecture.md`<br>`docs/prd.md`<br>`README.md` |

---

## 5. Phase-Wise Roadmap Alignment

Directly mirroring the 4 phases defined in [ImplementationPlan.md](file:///c:/Users/GS/Desktop/Incident%20Intelligence/ImplementationPlan.md):

```
Phase 1 ──► [ Foundation & Scaffolding: FastAPI, Groq Client (llama-3.3-70b-versatile), Atlassian MCP Bridge ]
Phase 2 ──► [ Core Retrieval & Grounding: Scoped JQL Translator (PROJECT in (...)), Retriever, Semantic Filter ]
Phase 3 ──► [ Pattern Synthesis & Learning Loop: Majority Engine (>50%), Stats Calculator, KB Writer (MCP Write-Back) ]
Phase 4 ──► [ Client Deliverables: Interactive CLI (rich), Dark-Mode Web UI & Modal, Weekly Summary Mode ]
```

| Phase | Milestone & Engineering Focus | Target Code & Deliverable Outputs |
| :---: | :--- | :--- |
| **Phase 1** | **Foundation, Environment Scaffolding & MCP Setup** | Scaffolding directory tree (`backend/`, `cli/`, `ui/`, `tests/`), configuring `requirements.txt` and `.env`, building `GroqClientWrapper` with rate-limit caching (`llm_client.py`), and establishing the `Atlassian MCP Client` protocol bridge (`mcp_client.py`). |
| **Phase 2** | **Core Matching Logic & Retrieval Grounding Engine** | Implementing `jql_translator.py` with mandatory project scoping (`PROJECT in ("CREP")`), building candidate retrieval (`retriever.py`), and deploying `semantic_filter.py` using Groq to filter out keyword-only false positives. |
| **Phase 3** | **Majority Pattern Synthesis & Confidence Guardrails** | Building `pattern_engine.py` (`< 3 matches` sparse warning + `>50%` majority rule extraction), computing date ranges (`stats_calculator.py`), and implementing the Continuous Learning Loop (`kb_writer.py` / `learning_loop.py` / `data/kb_store.json`). |
| **Phase 4** | **Deliverables — CLI, Web Chat UI & Weekly Summary** | Developing the interactive terminal app (`cli/run.py`), dark-mode triage web application (`ui/index.html` with 1-click resolution modal), and team lead weekly clustering (`backend/weekly_summary.py`). |

---

## 6. Tools & Technology Stack

| Tool / Technology | Architectural Role & Justification |
| :--- | :--- |
| **Groq Cloud API (`llama-3.3-70b-versatile`)** | High-speed, high-reasoning LLM engine responsible for JQL query translation, semantic false-positive filtering, and `>50%` majority-rule precursor/owner extraction. Optimized via caching to respect **30 RPM / 12,000 TPM** limits. |
| **Atlassian MCP Server (`mcpservers.org`)** | Model Context Protocol (`MCP`) protocol server executing `jira_search_issues`, `jira_add_comment`, and `jira_create_issue` over OAuth/API tokens without custom REST API boilerplate. |
| **FastAPI & Uvicorn (Python 3.11+)** | High-performance asynchronous backend server (`backend/main.py`) exposing triage and resolution capture endpoints (`/api/v1/query`, `/api/v1/capture-resolution`) with sub-millisecond route overhead. |
| **Pydantic v2** | Enforces strict runtime data validation and clean JSON schema definitions across all API requests, responses, candidate payloads, and KB entries (`backend/models.py`). |
| **Rich / Colorama (`CLI`)** | Terminal presentation framework (`cli/run.py`) rendering real-time pipeline status spinners and colorized, scannable pattern cards. |
| **Vanilla HTML5 / CSS3 / ES6 (`Web UI`)** | Lightweight, high-contrast dark-mode web application (`ui/index.html`, `ui/app.js`) designed for rapid 2am triage with zero frontend bundler or framework bloat. |
| **Antigravity IDE & GitHub** | Agentic pair-programming workspace used for engineering execution, automated testing (`pytest tests/`), version control, and portfolio documentation hosting. |

---
*Updated to fully incorporate the Atlassian MCP, Groq (`llama-3.3-70b-versatile`), and Continuous Learning Loop architecture established in `ImplementationPlan.md`.*
