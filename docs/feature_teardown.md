# Feature Teardown: PagerDuty's AI-Assisted Incident Response

*Reverse-engineering the PM decisions behind PagerDuty's AI features—and how Incident Intelligence takes a different approach.*

---

## 1. Why PagerDuty

PagerDuty is the dominant incident management platform and has invested heavily in AI features. Studying their architecture reveals what they chose to build, the tradeoffs they accepted, and the critical gap they left open for production support engineers.

---

## 2. PagerDuty's AI Features & PM Decisions

| Feature | What It Does | PM Decision & Optimization Goal | Metric Optimized |
| :--- | :--- | :--- | :--- |
| **AIOps (Alert Grouping)** | Uses ML on alert metadata (service, severity, timing) to cluster noisy alerts into a single incident. | **Reduce triage volume:** Turn 50 raw alerts into 5 actionable incidents. | Alert-to-incident compression ratio & MTTA |

| **Suggested Responders** | Recommends who to page based on historical response patterns and on-call schedules. | **Optimize routing speed:** Get the right human onto the incident faster. | Time to first human response |

| **Past Incidents** | Surfaces a list of historical incidents with similar titles or service metadata. | **Provide surface-level context:** Basic similarity matching without analyzing resolution quality. | MTTA & routing accuracy |

---

## 3. The Tradeoff: Routing vs. Resolution

PagerDuty made a clear architectural choice: **optimize for alert routing and acknowledgment speed, not resolution knowledge.**

### Why PagerDuty Made This Choice
1. **Business Model Alignment:** As a seat-based SaaS for on-call alerting, PagerDuty monetizes alert volume and routing efficiency, not debugging quality.
2. **Data Scalability:** Alert metadata (time, service, severity) is structured and uniform across customers. Resolution knowledge is unstructured, messy, and domain-specific.
3. **Procurement Focus:** Enterprise buyers actively seek to reduce **MTTA (Mean Time to Acknowledge)**—a clean, easily provable metric in sales cycles.

### PagerDuty vs. Incident Intelligence
| Dimension | PagerDuty's Choice | Incident Intelligence |
| :--- | :--- | :--- |
| **Primary Optimization** | Get the right person onto the incident fast | Give whoever is on the incident the knowledge to resolve it fast |
| **Knowledge Source** | Alert metadata (service, severity, timing) | Historical resolution context (what worked, why, and what failed) |
| **Similarity Signal** | Title text similarity + service overlap | Semantic similarity of problem descriptions + resolution patterns |
| **Primary Beneficiary** | On-call scheduler / Incident Commander | The frontline L2 engineer debugging at 2am |
| **Resolution Context** | Minimal (links to past incidents, no fix details) | Rich (exact resolution steps, root cause, source Jira tickets) |

---

## 4. What's Missing (The Gap)

1. **No Team-Specific Knowledge Accumulation:** PagerDuty treats incidents as independent, ephemeral events. Once resolved, knowledge is archived and forgotten; engineers immediately leave PagerDuty to search Jira and Slack.
2. **"Similar Incidents" Lacks Fix Context:** Showing past incident titles without showing *what actually fixed them*, how long it took, or what failed is like a library catalog without books.
3. **No Learning from Resolutions:** PagerDuty's ML learns which alerts co-occur, but never learns which fixes work for which errors or which root causes recur.
4. **One-Size-Fits-All Across Teams:** A Client Reporting team's failure taxonomy differs completely from Trade Settlement. A uniform global model generates noise; teams need isolated knowledge spaces.

---

## 5. What I'd Do Differently (→ Incident Intelligence)

Every major architectural decision in Incident Intelligence directly addresses PagerDuty's intentional trade-offs:

- **Decision 1: Resolution-First, Not Alert-First:** Start with the problem description and surface *knowledge*, assuming information—not routing—is the bottleneck.
- **Decision 2: Team-Specific Knowledge Spaces:** Isolate knowledge bases by team to prevent cross-departmental noise and match domain-specific vocabulary.
- **Decision 3: Human-Curated Knowledge Ingestion:** Prioritize high-quality manual curation (pasting email threads, submitting problem-solution snippets, importing Jira exports) over generic metadata extraction.
- **Decision 4: Explainable Confidence Scores:** Display exact matching signals (*"92% match: same error category, similar keywords, occurred 3x in 6 months"*) so engineers can trust suggestions during high-pressure P1s.

---

## 6. The Story Arc

| Step | What It Demonstrates |
| :--- | :--- |
| **1. PagerDuty Teardown** | Ability to deconstruct a market leader's strategy and articulate the PM decisions behind their features. |
| **2. Gap Identification** | Ability to spot where a dominant product's intentional tradeoffs leave frontline user needs underserved. |
| **3. "What I'd Do Differently"** | Architectural decisions are not random; they directly solve the missing capabilities identified in the teardown. |
| **4. Incident Intelligence Prototype** | Ability to execute across the entire product lifecycle—from strategic analysis to functional artifact. |
