# Incident Pattern Analysis: Client Reporting Team

*Data-driven analysis of incident patterns for a Client Reporting production support team. This analysis informed the design decisions in the PRD and prototype.*

---

## Purpose

This analysis serves two goals:
1. **Inform V1 design:** Which incident categories are most common? Which take the longest to resolve? Where would an AI resolution assistant have the most impact?
2. **Demonstrate PM-level data thinking:** Show that product decisions aren't gut-feel — they're grounded in data patterns, even when working with realistic mock data.

The data below represents a synthetic dataset modeled on actual incident patterns I've observed on the Client Reporting team. The distribution of categories, resolution times, and recurrence patterns are realistic.

---

## Dataset Overview

| Metric | Value |
|---|---|
| **Time period** | 6 months (Jan – Jun) |
| **Total incidents** | 127 |
| **Average incidents/month** | 21.2 |
| **Unique alert types** | 34 |
| **Average MTTR (all severities)** | 52 minutes |
| **P1/P2 incidents** | 38 (29.9%) |
| **Recurring patterns (≥3 occurrences)** | 12 |

---

## Incident Distribution by Category

| Category | Count | % of Total | Avg MTTR (min) | Recurring? |
|---|---|---|---|---|
| **Statement Generation** | 41 | 32.3% | 58 | Yes — 7 recurring patterns |
| **Reconciliation** | 34 | 26.8% | 67 | Yes — 3 recurring patterns |
| **Data Queries** | 28 | 22.0% | 35 | Partially — 2 patterns |
| **Delivery** | 16 | 12.6% | 42 | Rarely |
| **Other / Unclassified** | 8 | 6.3% | 78 | No |

### What This Tells Me

**Statement Generation and Reconciliation account for 59% of all incidents and have the highest MTTR.** These are the categories where an AI resolution assistant would have the most impact — they're frequent, time-consuming, and heavily recurring.

**Data Queries are frequent but resolve faster** — usually because they're informational ("ops is asking about a number that looks wrong") rather than system failures. Less need for historical resolution matching; more need for data lookup tools.

**"Other / Unclassified" has the highest MTTR (78 min)** — this is the long tail of novel problems. These are incidents where nobody has seen the pattern before, so there's no prior knowledge to draw from. *This is exactly the cold-start scenario I need to design for in the submission form.*

---

## Top 10 Recurring Incident Patterns

These are the patterns that recur 3+ times in 6 months. This is where Incident Intelligence has the clearest value proposition — if these had been surfaced by the tool on the 2nd occurrence, hours of search time could have been saved.

| Rank | Pattern | Category | Occurrences | Avg MTTR | Avg Search Time* | Resolution Known? |
|---|---|---|---|---|---|---|
| 1 | PDF renderer timeout on large batch (>500 statements) | Statement Gen | 8 | 62 min | 35 min | Yes — increase heap allocation |
| 2 | Reconciliation balance mismatch — FX rate timing | Reconciliation | 6 | 71 min | 40 min | Yes — rerun with T+1 rates |
| 3 | Missing client data in statement — upstream feed delay | Statement Gen | 5 | 55 min | 30 min | Yes — wait for feed, regenerate |
| 4 | Duplicate entries in recon report — idempotency failure | Reconciliation | 5 | 68 min | 45 min | Yes — deduplicate and rerun |
| 5 | Statement template rendering error — special characters | Statement Gen | 4 | 48 min | 25 min | Yes — escape characters in template |
| 6 | NAV calculation discrepancy — rounding precision | Reconciliation | 4 | 82 min | 50 min | Partial — depends on fund type |
| 7 | Client portal upload failure — file size limit | Delivery | 4 | 38 min | 20 min | Yes — split into chunks |
| 8 | Batch job timeout — database connection pool exhaustion | Statement Gen | 3 | 75 min | 40 min | Yes — restart connection pool |
| 9 | Wrong reporting period in generated statement | Statement Gen | 3 | 42 min | 30 min | Yes — verify date parameter |
| 10 | Regulatory format error — MiFID II field missing | Delivery | 3 | 55 min | 35 min | Yes — add missing field mapping |

*\*Avg Search Time = estimated time spent by the engineer searching for prior resolutions before beginning the actual fix. Based on observation and teammate conversations.*

### The Key Insight

**For 9 out of 10 of the top recurring patterns, the resolution is already known.** The problem isn't diagnosis — it's knowledge retrieval. An AI resolution assistant that matches an incoming error description against these patterns and surfaces the known resolution would eliminate an estimated **30-45 minutes of search time per incident**.

**Back-of-envelope impact for these 10 patterns alone:**
- 49 total occurrences × 35 min avg search time = **1,715 minutes (28.6 hours) of search time over 6 months**
- If Incident Intelligence saves 50% of that: **~14 hours saved over 6 months, just for the top 10 patterns**
- Full knowledge base coverage (all 34 alert types) would multiply this significantly

---

## Resolution Time Analysis

### MTTR by Severity

| Severity | Count | Avg MTTR (min) | Median MTTR (min) | 90th Percentile |
|---|---|---|---|---|
| **P1** | 12 | 78 | 72 | 120 |
| **P2** | 26 | 61 | 55 | 95 |
| **P3** | 54 | 45 | 40 | 75 |
| **P4** | 35 | 32 | 28 | 50 |

### MTTR Breakdown: Search Time vs. Fix Time

This is the analysis that convinced me the product should focus on knowledge retrieval, not incident diagnosis.

| Severity | Avg Total MTTR | Avg Search Time | Avg Fix Time | Search as % of MTTR |
|---|---|---|---|---|
| **P1** | 78 min | 38 min | 40 min | **48.7%** |
| **P2** | 61 min | 32 min | 29 min | **52.5%** |
| **P3** | 45 min | 22 min | 23 min | **48.9%** |
| **P4** | 32 min | 14 min | 18 min | **43.8%** |

**Nearly half of MTTR is search time, not fix time.** This holds consistently across all severity levels. The proportion is slightly higher for P2s, likely because P1s have stronger institutional knowledge (they're dramatic enough that everyone remembers them) and P4s are routine enough that engineers have memorized the fixes.

**P2s are the sweet spot for Incident Intelligence:** They're serious enough that the resolution matters, frequent enough that patterns exist, but not dramatic enough that everyone already knows the answer. Targeting P2 MTTR reduction is the most impactful V1 metric.

---

## Monthly Trend Analysis

| Month | Total Incidents | P1/P2 Count | Avg MTTR | New Patterns | Repeat Patterns |
|---|---|---|---|---|---|
| January | 18 | 5 | 58 min | 12 | 6 |
| February | 22 | 7 | 55 min | 8 | 14 |
| March | 19 | 6 | 51 min | 5 | 14 |
| April | 24 | 8 | 53 min | 4 | 20 |
| May | 21 | 6 | 49 min | 3 | 18 |
| June | 23 | 6 | 48 min | 2 | 21 |

### What I Notice

1. **New patterns decline over time.** By June, almost all incidents are variations of known patterns. This validates the core product thesis — a knowledge base with good coverage would surface relevant results for the vast majority of incidents.

2. **MTTR slowly decreases** — likely because the team is getting more experienced and recognizing patterns faster. But the improvement is gradual (~2 min/month). Incident Intelligence could accelerate this curve dramatically for new joiners.

3. **April spike (24 incidents, 8 P1/P2)** — this coincides with quarter-end processing, which generates higher load on statement generation and reconciliation systems. *This is a good scenario to demo: "Quarter-end incident surge — why a knowledge base matters most when the team is under pressure."*

---

## Knowledge Gap Analysis

Of the 34 unique alert types observed over 6 months:

| Knowledge Status | Count | % of Alert Types |
|---|---|---|
| **Well-documented** (Jira ticket with clear resolution) | 11 | 32.4% |
| **Partially documented** (Jira ticket exists, resolution vague) | 9 | 26.5% |
| **Undocumented** (resolution in someone's head or email) | 10 | 29.4% |
| **Unresolved** (no known good resolution) | 4 | 11.8% |

**Only 32% of alert types have well-documented resolutions.** That means for 2 out of 3 incidents, the engineer is either searching through incomplete documentation or relying on tribal knowledge.

**This is the knowledge base coverage gap that V1 needs to close.** The target metric of ">70% coverage within 3 months" in the PRD is ambitious but achievable if the team actively contributes — there are only 34 alert types to cover.

---

## Implications for V1 Design

| Analysis Finding | V1 Design Decision |
|---|---|
| Statement Gen + Reconciliation = 59% of incidents | Pre-seed the knowledge base with entries for these two categories |
| P2s have the highest search-time-to-MTTR ratio | Target P2 MTTR reduction as the primary success metric |
| Top 10 recurring patterns have known resolutions | Use these as the demo scenarios for the AI chat prototype |
| Knowledge gap: 68% poorly or undocumented | Prioritize the submission form and knowledge ingestion UX |
| New patterns decline over time | The knowledge base ROI increases with usage — design for long-term retention |
| Quarter-end spikes | Include time-based filtering in the dashboard ("show me patterns from last quarter-end") |

---

## Methodology Note

This data is synthetic but structurally realistic. The distributions, resolution times, and recurrence patterns are modeled on:
- Incident volumes I've observed on my team's Jira board
- MTTR ranges from conversations with teammates
- Category splits based on actual ticket labels used by the Client Reporting team
- Recurrence patterns based on which alerts I've seen my teammates triage multiple times

In a production deployment, this analysis would be generated automatically from Jira data exports and PagerDuty incident logs. The prototype will include a mock version of this analysis in the dashboard.

---

*This analysis demonstrates that the problem Incident Intelligence solves — knowledge retrieval during incident response — accounts for nearly 50% of total resolution time. The data supports building a tool focused on knowledge reuse rather than alert routing.*
