# Phase-Wise Implementation Plan: Incident Intelligence (v1 Prototype)
**An AI-Powered Pattern Recognition & Incident Triage Assistant via Atlassian MCP & Groq (`llama-3.3-70b-versatile`)**
*Incorporating Master Edge Cases, Circuit Breakers & Graceful Degradation Architecture ([edgeCases.md](file:///c:/Users/GS/Desktop/Incident%20Intelligence/edgeCases.md))*

---

## 1. Executive Summary & Goal

Aligned with [problemStatement.md](file:///c:/Users/GS/Desktop/Incident%20Intelligence/problemStatement.md) and [ArchitecturePlan.md](file:///c:/Users/GS/Desktop/Incident%20Intelligence/ArchitecturePlan.md), this implementation plan outlines the engineering roadmap to solve the **"2am P1 Triage Crisis"** while enforcing complete system resilience against the operational gotchas and anomaly scenarios identified in [edgeCases.md](file:///c:/Users/GS/Desktop/Incident%20Intelligence/edgeCases.md).

When a critical P1 alert fires at 2am (e.g., during overnight statement generation `stmt_gen_eod` or reconciliation runs), frontline L1/L2 production support engineers waste **30–60 minutes** searching Jira and Slack asking: *"Have we seen this exact alert before? What caused it right before it triggered? Who resolved it, and what is the exact Jira ticket?"*

**Incident Intelligence (v1)** replaces this manual search with an agentic pattern-matching workflow over the **Atlassian MCP Server (`jira_search_issues`)** and **Groq Cloud (`llama-3.3-70b-versatile`)**. Operating within a strict **10–15 second response SLA** and respecting Groq free-tier rate limits (**30 RPM / 12,000 TPM**), the system guarantees:
1. **Mandatory Project Scoping:** Translates queries into project-scoped JQL (`PROJECT in ("CREP") AND ... ORDER BY created DESC`), preventing global search leaks and `HTTP 400 JQL syntax crashes` (`EC-1.3`, `EC-1.4`).
2. **True Semantic Grounding & Overflow Protection:** Evaluates candidate tickets using `llama-3.3-70b-versatile` to verify root-cause alignment, applying automatic preprocessing truncation (`max 1500 chars` per trace / `max 500 chars` per description) to prevent token window overflow (`EC-1.1`).
3. **Majority-Rule Pattern Extraction:** Synthesizes recurrence counts, date ranges, dominant precursor conditions (`>50% majority rule`), and escalation owners (`>50% majority rule`) to prevent AI hallucination (`EC-3.2`).
4. **Confidence Guardrails & Offline Circuit Breakers:** Explicitly flags low confidence on `< 3 matches` (`EC-4.1`). If the Atlassian MCP Server disconnects (`Timeout > 3.0s`), trips an instant circuit breaker (`EC-2.1`) to serve verified local resolutions (`data/kb_store.json`) with zero SLA breach.
5. **Continuous Learning Loop & Idempotent Write-Back:** When engineers solve novel or sparse incidents (`< 3 matches`), a 1-click modal externalizes the exact fix steps back to Jira via Atlassian MCP (`jira_add_comment` / `jira_create_issue`) and `data/kb_store.json`. Enforces `SHA-256` deduplication hashes (`EC-5.1`) and dual storage fallbacks (`EC-5.2`), instantly prioritizing verified entries (`VERIFIED_KB_RESOLUTION`) on subsequent recurrences (`EC-4.2`).

---

## 2. External Dependencies & API Keys Required (USER ACTION ITEMS)

> [!IMPORTANT]
> **Before Phase 1 Execution, You Must Provide or Configure the Following External Credentials:**
> The agent cannot generate these external credentials or domain configurations on its own. Please gather these items and configure them in your environment (`.env` file and MCP client settings via `backend/config.py`).

| Step | Item / Key Name | Why It Is Required & Edge Case Governance | Where & How to Obtain |
| :---: | :--- | :--- | :--- |
| **1** | **Groq API Key**<br>`GROQ_API_KEY` | Powers the `llama-3.3-70b-versatile` model for JQL query translation, semantic ticket filtering, and precursor/owner pattern extraction under strict latency (`<15s`). Governed by rolling `30 RPM / 12,000 TPM` token budgeters (`EC-3.1`). | Register or log in at the [Groq Console API Keys Page](https://console.groq.com/keys) and generate a free API key (`gsk_...`). |
| **2** | **Atlassian Cloud Instance URL**<br>`ATLASSIAN_CLOUD_URL` | The base domain of your Atlassian Jira Cloud workspace targeted by the MCP server (e.g., `https://your-company.atlassian.net`). Protected against `HTTP 503` cloud maintenance circuit breaking (`EC-2.3`). | Copy the base domain URL from your browser when logged into your organization's Jira Cloud instance. |
| **3** | **Atlassian MCP Server Credentials**<br>`ATLASSIAN_MCP_CONFIG` | Connects via `stdio` or `SSE` transport to `mcpservers.org`. Executes `jira_search_issues`, `jira_add_comment`, and `jira_create_issue` tool calls. Includes synchronous `HTTP 401` token refresh handling (`EC-2.2`). | Setup an **Atlassian OAuth Client** (`Client ID` & `Client Secret`) at [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/) or provide your Atlassian API Token for local MCP bridge execution. |
| **4** | **Target Jira Project Keys**<br>`JIRA_PROJECT_KEYS` | JQL searches **must** be explicitly scoped to your team's specific projects (`CREP,OPS`). Searching all of Jira (`text ~ "exception"`) is structurally blocked to prevent compliance violations and OOM query crashes (`EC-1.3`). | Check your Jira board or URL for the exact project keys corresponding to your team (e.g., `CREP` for Client Reporting). |

---

## 3. End-to-End Architectural & Resilience Flow ("Definition of Done")

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 1. ENGINEER INPUT (2am, Half-Asleep)                                             │
│    "MemoryPoolExhaustedException on app-client-rep-04 during stmt_gen_eod batch" │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 2. INPUT SANITIZATION & CACHE CHECK (`backend/models.py` | `backend/cache.py`)   │
│    • EC-1.2 Check: Verify min_length=10 and distinct error signature (`len>=25`).│
│    • EC-3.1 Check: Check LRUCache (MD5 hash of normalized alert).                │
│      ► IF CACHE HIT: Return cached PatternResponse (< 50ms, 0 Groq tokens used). │
│      ► IF CACHE MISS: Execute Stage 3.                                           │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 3. INTENT & SCOPED JQL EXTRACTION (`jql_translator.py` via Groq API)             │
│    • EC-1.1 Check: Truncate input to max 1500 chars to prevent prompt overflow.  │
│    • EC-1.4 Check: Escape JQL reserved characters (`[ ] ( ) + - ! * ? ~ ^`).     │
│    • EC-1.3 Check: Enforce non-bypassable scoping:                               │
│      PROJECT in ("CREP") AND (text ~ "MemoryPoolExhausted" OR text ~             │
│      "stmt_gen_eod") ORDER BY created DESC                                       │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 4. RETRIEVAL VIA ATLASSIAN MCP SERVER (`retriever.py` | `mcp_client.py`)         │
│    • Tool Call: `jira_search_issues` (Returns top 15-25 candidate payloads).     │
│    • EC-2.1 Check: If MCP unresponsive (`Timeout > 3.0s`), open circuit breaker  │
│      and instantly switch to Local Knowledge Fallback Mode (`data/kb_store.json`)│
│    • EC-2.2 Check: If HTTP 401 Unauthorized, execute sync token refresh (<500ms).│
│    • EC-2.3 Check: If 0 candidates returned (`[]`), output novel error prompt.   │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 5. SEMANTIC GROUNDING & FILTERING (`semantic_filter.py` via Groq API)            │
│    • EC-1.1 Check: Truncate candidate description (`max 500 chars` + top 3       │
│      comments) to guarantee prompt stays under 3,500 token limit.                │
│    • Evaluates true semantic root cause, filtering out keyword false positives.  │
│    • EC-3.1/3.3 Check: If Groq hits HTTP 429 or timeout (>4.5s), gracefully      │
│      degrade to Deterministic Keyword Matching Engine (`< 12.0s SLA preserved`). │
│    • EC-4.2 Check: If any ticket has verified `[INCIDENT_INTELLIGENCE_KB_ENTRY]` │
│      comment tag, assign `confidence_score = 1.0` and highest priority boost.    │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 6. MAJORITY PATTERN SYNTHESIS & GUARDRAILS (`pattern_engine.py`)                 │
│    • Guardrail Check (`EC-4.1`): Are there >= 3 verified semantic matches?       │
│      ► IF NO (< 3 matches and no `[KB_ENTRY]`): Return explicit low-confidence   │
│        warning (`LOW_CONFIDENCE_SPARSE`) with 1-2 direct clickable Jira links.   │
│      ► IF YES (>= 3 matches OR `[KB_ENTRY]` exists): Execute synthesis:          │
│        - Recurrence Count & Exact Date Range (`stats_calculator.py`)             │
│        - Precursor Condition (`EC-3.2`: Enforce >50% majority rule check across  │
│          tickets; if varied without >50% consensus, state "varied triggers")     │
│        - Escalation Owner (`EC-3.2`: Enforce >50% majority rule check)           │
│        - Top 2-3 Clickable Jira URLs (`browse/CREP-104`)                         │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 7. STRUCTURED OUTPUT DELIVERED IN < 10-15 SECONDS (`FastAPI` | `UI` | `CLI`)     │
│    Clean, scannable pattern card ready for immediate escalation or RCA adoption. │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 8. CONTINUOUS LEARNING LOOP & IDEMPOTENT WRITE-BACK (`kb_writer.py`)             │
│    • Trigger: Engineer solves novel or sparse issue (< 3 matches), inputs fix    │
│      into UI/CLI modal (`alert_trace`, `precursor`, `fix_steps`, `owner`).       │
│    • EC-5.3 Check: Enforce Pydantic validation (`precursor min 15 chars`, `fix   │
│      min 30 chars`). Reject blank (`"fixed it"`) submissions cleanly.            │
│    • EC-5.1 Check: Compute `SHA-256(alert_signature + precursor)`. Deduplicate   │
│      against `kb_store.json` and ticket comments across a 30-minute window to    │
│      prevent duplicate tickets during concurrent shift responses.                │
│    • Write-Back: Call `jira_add_comment` (or `jira_create_issue` for new Known   │
│      Error tickets) and append to `data/kb_store.json`.                          │
│    • EC-5.2 Check: If Jira read-only (`HTTP 403 / 503`), execute Dual Storage    │
│      Fallback: log to `pending_jira_sync.log` and save to local `kb_store.json`. │
│    • Next Recurrence: `CandidateRetriever` & `SemanticFilter` detect verified    │
│      `[KB_ENTRY]` block and output exact fix instantly (`VERIFIED_KB_RESOLUTION`).│
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phase-Wise Implementation Roadmap (Enriched with `edgeCases.md`)

We break down the development into **4 sequential phases**. Every step specifies exact code targets, architectural requirements, explicit edge case mitigations (`EC-X.X`), and verification checks.

---

### Phase 1: Foundation, Environment Scaffolding & Circuit Breaker Setup
**Goal:** Establish the Python backend execution environment, configure the `llama-3.3-70b-versatile` Groq wrapper with strict token budgeting and caching, and scaffold the Atlassian MCP protocol bridge with timeout circuit breakers.

#### Step 1.1: Project Directory, Dependencies & Pydantic Config Layer
- **Actions:** Create structure (`backend/`, `cli/`, `ui/`, `data/`, `tests/`). Create `requirements.txt` (`fastapi`, `uvicorn`, `groq`, `mcp`, `pydantic`, `pydantic-settings`, `python-dotenv`, `rich`). Build `backend/config.py` using `Settings` class (`pydantic-settings`) to validate critical environment keys (`GROQ_API_KEY`, `ATLASSIAN_CLOUD_URL`, `ATLASSIAN_MCP_CONFIG`, `JIRA_PROJECT_KEYS`).
- **Edge Case Governance:**
  - Enforce presence of non-empty `JIRA_PROJECT_KEYS` on startup (`EC-1.3`).
  - Configure global `FastAPI` exception handlers in `backend/main.py` to intercept `HTTP 422 Unprocessable Entity` validation errors (`EC-5.3`) and return clean JSON payloads.
- **Target Files:** `requirements.txt`, `.env.example`, `backend/__init__.py`, `backend/config.py`, `backend/main.py`.

#### Step 1.2: Groq LLM Client Wrapper, LRU Cache & Rate-Limit Backoff Engine
- **Actions:** Build `backend/llm_client.py` (`GroqClientWrapper`) targeting `llama-3.3-70b-versatile` via the `groq` SDK. Build `backend/cache.py` (`LRUCache`) using in-memory dict or SQLite with a `15-minute TTL` and `MD5` alert trace hashing.
- **Edge Case Governance (`EC-3.1`, `EC-3.3`):**
  - **Active Outage Repeat Interception (`EC-3.1`):** Check `LRUCache` before any Groq API invocation. Serve exact matches in `< 50ms` (`0 tokens consumed`).
  - **Throttling & Backoff State Machine (`EC-3.1`):** Track rolling `TPM` against the `12,000 TPM` free-tier ceiling. When consumption crosses 85% (`10,200 TPM`) or Groq returns `429 Too Many Requests`, execute exponential backoff jitter (`0.5s -> 1.0s -> 2.0s`).
  - **Stage Timeout Circuit Breaker (`EC-3.3`):** Enforce a `4.5 second` timeout on all Groq generation requests. If timeout occurs, catch `GroqTimeoutError` and signal pipeline fallback.
- **Target Files:** `backend/llm_client.py`, `backend/cache.py`.

#### Step 1.3: Atlassian MCP Client Scaffolding & Resilience Bridge (`jira_search_issues`)
- **Actions:** Build `backend/mcp_client.py` connecting to Atlassian MCP Server (`mcpservers.org`) over `stdio` or `SSE`. Implement tool wrappers: `execute_jira_search(jql, max_results=20)`, `execute_add_comment(issue_key, comment)`, and `execute_create_issue(project, summary, description)`.
- **Edge Case Governance (`EC-2.1`, `EC-2.2`, `EC-2.3`):**
  - **Connection Circuit Breaker (`EC-2.1`):** Enforce a strict `3.0 second` connection/execution timeout on all MCP tool invocations. If unreachable, trip circuit breaker and raise `McpConnectionError` triggering offline fallback.
  - **Synchronous Token Refresh (`EC-2.2`):** Intercept `HTTP 401 Unauthorized`, execute a `< 500ms` token refresh using `ATLASSIAN_MCP_CONFIG` refresh tokens, and retry tool call once.
  - **Cloud Maintenance Isolation (`EC-2.3`):** Intercept `HTTP 503 Service Unavailable`, open Atlassian circuit breaker (`300s TTL`), and route all requests to local `data/kb_store.json`.
- **Target Files:** `backend/mcp_client.py`.

#### Verification Criteria (Phase 1)
- `pytest tests/test_mcp_resilience.py` -> verifies circuit breaker opens after `3.0s` timeout (`EC-2.1`) and successfully catches `401 Unauthorized` token refresh (`EC-2.2`).
- `pytest tests/test_llm_cache_and_backoff.py` -> verifies `LRUCache` returns cached payload in `< 50ms` (`EC-3.1`) and correctly retries on simulated `429` rate limit (`EC-3.1`).

---

### Phase 2: Core Matching Logic & Retrieval Grounding Engine
**Goal:** Implement the explicit two-stage retrieval and semantic similarity grounding pipeline that strictly scopes JQL queries, truncates massive traces, and eliminates keyword false positives.

#### Step 2.1: Scoped JQL Query Translator with Sanitization & Anti-Injection Guardrails
- **Actions:** Build `backend/jql_translator.py` formatting raw alerts into `JQL_TRANSLATION_PROMPT` to extract distinctive keywords via `llama-3.3-70b-versatile`.
- **Edge Case Governance (`EC-1.1`, `EC-1.3`, `EC-1.4`):**
  - **Input Preprocessing Truncation (`EC-1.1`):** Execute `truncate_alert_trace(alert_trace, max_chars=1500)` before passing trace to Groq to prevent prompt overflow.
  - **Sanitization & Escaping (`EC-1.4`):** Apply `escape_jql_terms()` to sanitize unescaped JQL reserved characters (`[ ] ( ) + - ! * ? ~ ^`) and prevent `HTTP 400 JQL syntax crashes`.
  - **Non-Bypassable Scoping Guardrail (`EC-1.3`):** Strip explicit `PROJECT in (...)` strings from LLM output or user input. Forcefully prefix `PROJECT in ("{JIRA_PROJECT_KEYS}") AND ` and append ` ORDER BY created DESC`.
- **Target Files:** `backend/jql_translator.py`.

#### Step 2.2: Candidate Ticket Retrieval via MCP & Offline Fallback Controller
- **Actions:** Build `backend/retriever.py` calling `mcp_client.execute_jira_search(jql, max_results=20)` and parsing JSON payloads (`summary`, `description`, `comments`, `created`, `assignee`) into `List[JiraTicketCandidate]`.
- **Edge Case Governance (`EC-1.4`, `EC-2.1`, `EC-2.3`):**
  - **400 Syntax Error Catch (`EC-1.4`):** If Atlassian Jira returns `400 Bad Request`, strip complex operators and retry once with alphanumeric keyword search.
  - **Offline Local KB Fallback (`EC-2.1`):** If `McpConnectionError` is caught, switch to `OfflineFallbackMode`. Scan `data/kb_store.json` for alert signatures. If matched, return `VERIFIED_KB_RESOLUTION` with warning banner (`< 0.2s`).
  - **Zero Retrieval Handling (`EC-2.3`):** If search returns `[]` (novel error), return empty list `[]` to signal `NO_MATCHES_FOUND` prompt.
  - **Verified KB Tag Scan (`EC-4.2`):** Scan `data/kb_store.json` and candidate comments for `[INCIDENT_INTELLIGENCE_KB_ENTRY]`. If detected, mark `candidate.has_verified_kb_entry = True`.
- **Target Files:** `backend/retriever.py`.

#### Step 2.3: Semantic Grounding Filter & Truncation Engine
- **Actions:** Build `backend/semantic_filter.py` (`SemanticFilter`). Batches candidate tickets and alert trace into `SEMANTIC_GROUNDING_PROMPT` using `llama-3.3-70b-versatile` to assign `is_semantic_match: bool` and `confidence_score: float` (`0.0–1.0`).
- **Edge Case Governance (`EC-1.1`, `EC-1.2`, `EC-3.1`, `EC-3.3`, `EC-4.2`):**
  - **Candidate Truncation (`EC-1.1`):** Truncate each candidate's `description` (`max 500 chars`) and isolate only the **top 3 most recent comments** to keep multi-ticket evaluation prompts under `3,500 tokens`.
  - **Ambiguity Noise Rejection (`EC-1.2`):** For generic short queries (`len < 25`), enforce strict root-cause matching, scoring generic candidates `< 0.50` (`NO_MATCHES_FOUND`).
  - **Verified KB Priority Boost (`EC-4.2`):** If any candidate possesses `has_verified_kb_entry = True`, assign `confidence_score = 1.0` and boost directly to top of verified list.
  - **Deterministic Keyword Fallback (`EC-3.1`, `EC-3.3`):** If Groq returns persistent `HTTP 429` or exceeds `4.5s` timeout, switch to **Deterministic Keyword Matching Engine** (scoring by exact term overlap and extracting latest ticket comment without LLM synthesis), preserving `SLA < 15.0s`.
- **Target Files:** `backend/semantic_filter.py`.

#### Verification Criteria (Phase 2)
- `pytest tests/test_jql_scoping.py` -> asserts `PROJECT in ("CREP")` is forcefully injected (`EC-1.3`), handles injection attempts cleanly (`EC-1.3`), and truncates 25,000-char stack traces to 1,500 chars (`EC-1.1`).
- `pytest tests/test_semantic_filter.py` -> verifies truncation of massive ticket descriptions (`EC-1.1`), rejection of keyword-only false positives (`EC-1.2`), priority boost for `has_verified_kb_entry` (`EC-4.2`), and clean fallback to deterministic keyword scoring on simulated LLM timeout (`EC-3.3`).

---

### Phase 3: Majority-Rule Pattern Synthesis & Continuous Learning Loop
**Goal:** Build the pattern extraction engine (`step 3` of requirements) enforcing confidence thresholds, `>50%` majority checking, temporal stats, and the idempotent post-resolution write-back loop.

#### Step 3.1: Pattern Engine, Sparse Thresholds & Majority-Rule Prompts (`>50% Check`)
- **Actions:** Build `backend/pattern_engine.py` (`PatternEngine`) and `backend/prompts/pattern_prompts.py` (`MAJORITY_PATTERN_EXTRACTION_PROMPT`).
- **Edge Case Governance (`EC-3.2`, `EC-4.1`, `EC-4.2`, `EC-4.3`):**
  - **Sparse Threshold Check (`EC-4.1`):** If `len(verified_matches) == 0`: return `NO_MATCHES_FOUND` (`EC-4.3`). If `len(verified_matches) in [1, 2]` (and `has_verified_kb_entry == False`): return `LOW_CONFIDENCE_SPARSE`. Populate 1–2 clickable ticket links, but explicitly suppress generalized precursor and owner claims with warning: *"⚠️ Low Confidence: Only {count} historical match(es) found. This does not yet establish a verified recurring pattern."*
  - **Verified KB Priority Override (`EC-4.2`):** If `len == 1` or `2` but `has_verified_kb_entry == True`, assign `confidence_status = VERIFIED_KB_RESOLUTION`, overriding sparse checks and outputting the exact fix immediately.
  - **Anti-Hallucination Majority Rule (`EC-3.2`):** When `len >= 3`, pass concatenated ticket histories to `llama-3.3-70b-versatile` with strict instructions: **ONLY** declare a precursor condition if documented across **>50% of matched candidates**. If triggers vary across tickets without consensus, output exactly: `"No single dominant precursor condition across matches (varied triggers)."` and list individual sample tickets.
- **Target Files:** `backend/pattern_engine.py`, `backend/prompts/pattern_prompts.py`.

#### Step 3.2: Temporal Recurrence & Stats Calculation Engine
- **Actions:** Build `backend/stats_calculator.py` (`StatsCalculator`). Computes `created_timestamp` ranges across verified matches in `< 50ms`.
- **Outputs:** Exact recurrence count (`pattern_count`), date span (`date_range: "Jan 12, 2026 – Jul 02, 2026"`), and formatted summary string (`"11 times in 6 months"`).
- **Target Files:** `backend/stats_calculator.py`.

#### Step 3.3: Pydantic v2 Schema Validation Registry (`backend/models.py`)
- **Actions:** Define strict Pydantic v2 data models (`QueryRequest`, `JiraTicketCandidate`, `SemanticMatchResult`, `PatternResponse`, `ResolutionCaptureRequest`, `KnowledgeBaseEntry`).
- **Edge Case Governance (`EC-1.2`, `EC-5.3`):**
  - Enforce `QueryRequest.alert_trace (min_length=10)` (`EC-1.2`).
  - Enforce `ResolutionCaptureRequest.precursor_condition (min_length=15)` and `resolution_narrative (min_length=30)` (`EC-5.3`). Rejects blank (`"fixed it"`) or malformed resolution submissions before they pollute `[KB_ENTRY]` index.
- **Target Files:** `backend/models.py`.

#### Step 3.4: Continuous Learning Loop, Deduplication & KB Write-Back Engine
- **Actions:** Build `backend/kb_writer.py` and `backend/learning_loop.py` to power `JTBD 2: Post-Resolution Externalization`. Ingests `ResolutionCaptureRequest` and formats `[INCIDENT_INTELLIGENCE_KB_ENTRY]` markdown block.
- **Edge Case Governance (`EC-4.2`, `EC-5.1`, `EC-5.2`):**
  - **Concurrent Write-Back Deduplication (`EC-5.1`):** Compute `SHA-256(alert_signature + precursor_condition)`. Before invoking Atlassian MCP tools, scan `data/kb_store.json` and recent ticket comments across a `30-minute window`. If identical hash found, skip duplicate creation, merge any new fix notes, and return existing `kb_id` (`CREP-189`).
  - **Dual Storage & Read-Only Fallback (`EC-5.2`):** If `existing_issue_key` provided, execute `mcp_client.execute_add_comment(issue_key, kb_block)`. If null, execute `mcp_client.execute_create_issue("CREP", "[Known Error]...", kb_block)`. If Atlassian MCP throws `HTTP 403 / 503 Permission/Server Error` (read-only maintenance), log task to `pending_jira_sync.log` and save directly to `data/kb_store.json` (`sync_status = PENDING_JIRA_SYNC`).
  - **Instant Retrieval Boost (`EC-4.2`):** On any subsequent query (`count=1`), `retriever.py` and `semantic_filter.py` detect this `[KB_ENTRY]`, return `VERIFIED_KB_RESOLUTION`, and display the documented steps instantly.
- **Target Files:** `backend/kb_writer.py`, `backend/learning_loop.py`, `data/kb_store.json`.

#### Verification Criteria (Phase 3)
- `pytest tests/test_pattern_engine.py` -> verifies `< 3 matches` returns `LOW_CONFIDENCE_SPARSE` (`EC-4.1`), verifies `VERIFIED_KB_RESOLUTION` overrides sparse threshold on `count=1` (`EC-4.2`), and verifies `>50%` majority check outputs `"No single dominant precursor condition across matches (varied triggers)."` when triggers conflict (`EC-3.2`).
- `pytest tests/test_learning_loop.py` -> verifies `SHA-256` deduplication prevents duplicate Jira comments (`EC-5.1`), verifies `HTTP 403/503` triggers dual storage local fallback (`EC-5.2`), and verifies `Pydantic v2` rejects blank resolution submissions (`EC-5.3`).

---

### Phase 4: Deliverables — CLI, Minimal Chat Web UI & Weekly Summary Mode
**Goal:** Build the user-facing interfaces delivering structured results within ~10–15 seconds, surfacing clear offline/fallback badges, plus the shift lead weekly summary stretch goal.

#### Step 4.1: Interactive Terminal Client (`cli/run.py`, `cli/formatter.py`)
- **Actions:** Build sleek terminal app using `rich`/`colorama`. Displays real-time spinners (`Translating JQL -> Searching MCP -> Filtering -> Extracting`) and renders a colorized pattern card within ~10–15 seconds. Supports `--capture-resolution` terminal walkthrough and `--weekly-summary --project CREP --days 7`.
- **Edge Case Governance (`EC-2.1`, `EC-3.1`, `EC-4.1`):**
  - Render explicit visual warning banners if card status is `LOW_CONFIDENCE_SPARSE` (`EC-4.1`), if evaluated via deterministic keyword grouping (`EC-3.1`), or if operating in offline local KB mode (`EC-2.1`).
- **Target Files:** `cli/run.py`, `cli/formatter.py`.

#### Step 4.2: Dark-Mode Web Chat UI & Resolution Modal (`ui/index.html`, `ui/app.js`, `backend/main.py`)
- **Actions:** Build high-contrast dark-mode web app (`#0d1117` background, `#58a6ff` accents) served by FastAPI. Features prominent query textarea, scannable badge layout, clickable Jira links (`browse/CREP-104`), and a 1-click **"📝 Document New Resolution"** modal submitting to `/api/v1/capture-resolution`.
- **Edge Case Governance (`EC-2.1`, `EC-3.1`, `EC-5.1`, `EC-5.2`, `EC-5.3`):**
  - **Fallback Status Banners:** Dynamically display high-visibility warning banners at top of card when returning `LOW_CONFIDENCE_SPARSE` (`EC-4.1`), keyword fallback (`EC-3.1`), or Atlassian offline mode (`EC-2.1`).
  - **Inline Validation Feedback (`EC-5.3`):** Intercept `HTTP 422 Unprocessable Entity` when submitting the modal, displaying clear inline guidance (`"Please provide at least 30 characters detailing the step-by-step resolution so future shift engineers can apply this fix."`).
  - **Instant Success Toast (`EC-5.1`, `EC-5.2`):** Display instant confirmation toast upon resolution capture: *"✅ Resolution Documented & Indexed via Atlassian MCP!"* (or offline queue banner if Jira sync pending).
- **Target Files:** `backend/main.py`, `ui/index.html`, `ui/style.css`, `ui/app.js`.

#### Step 4.3: Shift Manager Weekly Summary Mode (`backend/weekly_summary.py`, `ui/summary_view.html`)
- **Actions:** Implement `/api/v1/weekly-summary?project=CREP&days=7` and `--weekly-summary`. Ingests `project_key` (`CREP`) and `days` (`7`). Constructs scoped JQL: `project in ("CREP") AND created >= -7d ORDER BY created DESC`. Fetches up to 50 recent incident tickets via Atlassian MCP, clusters them semantically using `llama-3.3-70b-versatile` (`WEEKLY_CLUSTER_PROMPT`), and returns **Top 3 Recurring Alerts by Frequency**.
- **Edge Case Governance (`EC-3.1`):** If Groq hits `HTTP 429` or timeout during weekly clustering, fallback to deterministic keyword/component grouping over the 50 fetched tickets.
- **Target Files:** `backend/weekly_summary.py`, `ui/summary_view.html`.

#### Verification Criteria (Phase 4)
- **End-to-End Latency Benchmarking:** Execute `python -m cli.run --benchmark --query "MemoryPoolExhaustedException during stmt_gen_eod"`. Ensure total execution wall-clock time across JQL, Atlassian MCP retrieval, semantic grounding, synthesis, and UI render completes in **< 15.0 seconds** under both normal and simulated fallback modes (`EC-3.1`, `EC-3.3`).
- **Scan-Ability Test:** Verify structured badges (`count`, `precursor`, `owner`, `URLs`, and any `EC-X.X` status banners) can be scanned by an L2 engineer in **< 10 seconds**.
- **Continuous Learning End-to-End Suite:** Submit novel error -> verify `NO_MATCHES_FOUND` (`EC-4.3`) -> open modal and submit resolution (`EC-5.3` check) -> verify deduplication hash created (`EC-5.1`) -> re-submit original error string -> verify instant `VERIFIED_KB_RESOLUTION` card (`EC-4.2`).

---

### Phase 6: Deliverables — Multi-Cloud Production Deployment Architecture (Vercel & Railway)
**Goal:** Deploy the complete production prototype seamlessly across **Railway** (FastAPI Backend Server & Persistent Knowledge Store) and **Vercel** (High-Contrast Dark-Mode Web UI & Serverless Proxy/Routing) with automated environment binding and zero-configuration CORS/routing.

#### Step 6.1: Railway Backend API Service & Persistent Volume Configuration (`Procfile`, `railway.json`, `requirements.txt`)
- **Actions:** Configure `Procfile` (`web: uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}`) and `railway.json` (`$schema`, `build.builder = "NIXPACKS"`, `deploy.restartPolicyType = "ON_FAILURE"`) for Python 3.11+ deployment. Update `requirements.txt` to include `requests>=2.31.0` alongside FastAPI, Uvicorn, Groq, Pydantic v2, and Rich. Configure CORS middleware (`allow_origins=["*"]`) and dynamic port binding (`os.getenv("PORT", 8000)`) in `backend/main.py`.
- **Edge Case Governance (`EC-2.1`, `EC-5.2`):**
  - **Ephemeral Container Resilience (`EC-5.2`):** Enforce persistent storage volume mount (`/app/data`) or local fallback file synchronization (`data/kb_store.json` & `pending_jira_sync.log`) so that new resolutions captured via Atlassian MCP or local dual-storage persist across Railway container restarts.
- **Target Files:** `Procfile`, `railway.json`, `requirements.txt`, `backend/main.py`.

#### Step 6.2: Vercel Static Frontend & API Reverse Proxy/Routing (`vercel.json`, `ui/app.js`)
- **Actions:** Configure `vercel.json` (`version: 2`) with static UI routing (`/ -> /ui/index.html`) and secure API proxy rewrites (`/api/v1/:path*` -> `https://incident-intelligence-api.up.railway.app/api/v1/:path*`). Modify `ui/app.js` to dynamically detect environment origin (`window.location.hostname` / `window.API_BASE_URL`): connecting to `http://localhost:8000/api/v1` locally and `/api/v1` on Vercel.
- **Edge Case Governance (`EC-2.1`, `EC-3.1`, `EC-5.1`):**
  - **Secure Proxy Boundary:** Reverse proxying `/api/v1` through Vercel eliminates CORS flight delays (`OPTIONS` overhead) and prevents exposure of internal backend endpoints, ensuring `< 15.0s` SLA (`EC-3.1`).
- **Target Files:** `vercel.json`, `ui/app.js`.

#### Verification Criteria (Phase 6)
- **Multi-Cloud Health & Triage Verification:** Access deployed Vercel domain (`https://incident-intelligence.vercel.app`), verify static assets render (`/style.css`, `/app.js`), submit P1 triage query (`Memory pool exhausted on node 04`), and verify response card is returned from Railway backend (`https://incident-intelligence-api.up.railway.app/api/v1/triage`) within `< 15.0s`.
- **External Environment Governance:** Verify all external environment variables (`GROQ_API_KEY`, `ATLASSIAN_CLOUD_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEYS`) are correctly injected on Railway Dashboard and Vercel Project Settings.

---

## 5. Summary Table of Deliverables & Rigorous Verification Plan

Every deliverable is linked directly to automated test verification and explicit edge case compliance criteria:

| Deliverable Scope | Component / Phase | Target Latency & Edge Case Criteria (`edgeCases.md`) | Automated Verification Command |
| :--- | :--- | :--- | :--- |
| **1. Scoped MCP Search & Truncation** | Phase 1 & Phase 2 | Enforces `PROJECT in ("CREP")` (`EC-1.3`); truncates 25k-char stack traces (`EC-1.1`); escapes JQL syntax (`EC-1.4`). | `pytest tests/test_jql_scoping.py` |
| **2. Atlassian MCP Resilience** | Phase 1 (`mcp_client.py`) & Phase 2 (`retriever.py`) | Circuit breaker opens on `Timeout > 3.0s` (`EC-2.1`) querying `kb_store.json`; catches `401 Unauthorized` token refresh (`EC-2.2`). | `pytest tests/test_mcp_resilience.py` |
| **3. Semantic Grounding & Rate Protection** | Phase 2 (`semantic_filter.py`) | Caches identical queries (`LRUCache`, `EC-3.1`); retries/backoffs on `HTTP 429` (`EC-3.1`); falls back to keyword matching on timeout (`EC-3.3`). | `pytest tests/test_semantic_filter.py` and `test_llm_cache_and_backoff.py` |
| **4. Majority Pattern & Confidence** | Phase 3 (`pattern_engine.py`) | Explicit warning if `< 3 matches` (`EC-4.1`); precursor/owner enforced by `>50%` majority rule (`EC-3.2`); checks `VERIFIED_KB_RESOLUTION` override (`EC-4.2`). | `pytest tests/test_pattern_engine.py` |
| **5. Continuous Learning & Idempotent KB** | Phase 3 (`kb_writer.py`) & Phase 4 (`ui/index.html`) | `SHA-256` deduplication (`EC-5.1`); `HTTP 403/503` local dual storage fallback (`EC-5.2`); `Pydantic v2` validation (`EC-5.3`); 1-click modal. | `pytest tests/test_learning_loop.py` and `python -m cli.run --capture-resolution` |
| **6. Interactive CLI & Fallback Banners** | Phase 4 (`cli/run.py`) | Displays colorized structured output card and offline/fallback banners (`EC-2.1`, `EC-3.1`, `EC-4.1`) in **< 15.0 seconds**. | `python -m cli.run --query "Memory pool exhausted on node 04"` |
| **7. Dark-Mode Web Chat UI & Modal** | Phase 4 (`ui/index.html` / `app.js`) | Dark-mode 2am triage UI, structured badge layout, clickable Jira links (`browse/CREP-104`), inline 422 validation, 1-click resolution capture modal. | `python -m backend.main` (open `http://localhost:8000`) |
| **8. Shift Lead Weekly Summary Mode** | Phase 4 (`weekly_summary.py`) | Returns exactly **Top 3 Recurring Alert Clusters** for project key over 7 days via Atlassian MCP (`created >= -7d`). | `python -m cli.run --weekly-summary --project CREP --days 7` |
| **9. Multi-Cloud Production Deployment** | Phase 6 (`vercel.json`, `railway.json`, `Procfile`) | Railway FastAPI backend + Vercel static UI reverse proxying (`/api/v1/:path*`), dynamic origin detection, CORS support, `< 15.0s` SLA (`EC-2.1`, `EC-3.1`, `EC-5.2`). | `python -c "import requests; print(requests.get('http://localhost:8000/api/v1/health').json())"` |

---
*Updated to fully incorporate Master Edge Cases, Circuit Breakers, and Multi-Cloud Production Deployment Architecture (Vercel & Railway).*
