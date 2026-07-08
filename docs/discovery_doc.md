# Discovery Document: Incident Intelligence

*A concise discovery document for an AI-powered incident resolution assistant for Client Reporting teams at a Tier-1 investment bank.*

---

## 1. Who Is Suffering

We are building for **L1/L2 production support engineers**—the frontline responders paged at 2am when jobs fails.

### Key Observations
- **Technical Capability:** Strong at diagnosing and fixing issues once root cause is understood.
- **The Bottleneck:** Finding historical context—specifically answering: *"Has this happened before, and what was the resolution?"*
- **Siloed Knowledge:** Senior engineers hold 60–70% of institutional knowledge in their heads. When they rotate or take leave, this knowledge vanishes.
- **New Joiner Friction:** Engineers with <6 months tenure resolve incidents significantly slower due to missing historical context, not lack of technical skill.

### Out of Scope (V1)
- **VPs / Senior Management:** Care about aggregate MTTR metrics, not real-time debugging.
- **Platform / Infra Engineers:** Own underlying systems; looped in only for major escalations.
- **Compliance / Audit:** Need post-facto reporting rather than active resolution tooling.

---

## 2. What Happens When an Incident Fires

### The Current Flow (Observed)

```
Alert fires (PagerDuty / Slack / Email)
    ↓
Engineer acknowledges alert
    ↓
Keyword search in Jira (15 results -> 12 irrelevant, 2 outdated)
    ↓
Scrolls Slack #client-reporting-incidents (noisy, 200+ msgs/day)
    ↓
Searches Email threads (resolution buried in reply #7 from 4 months ago)
    ↓
Pings senior teammate (5–10 min if online; escalate blind if offline)
    ↓
Resolves issue & occasionally documents in Jira
```

> **Search vs. Fix Time:** Engineers spend **30–60 minutes** asking *"have we seen this before?"* compared to just **5–15 minutes** implementing the actual fix.

### Voice of the Engineer (Real Observations)
- *"I spent 40 minutes on a P2 last Tuesday that turned out to be the exact same issue we fixed in March. I just didn't know how to find the old ticket because the error message was slightly different."*
- *"Every time someone new joins, I become their search engine for three months. 'Have you seen this before?'—yeah, five times, but it's not written down anywhere central."*
- *"I don't need AI to fix my incidents. I need it to tell me: here are the last three times this happened, here is what worked, and here is the Jira ticket."*

### Community Signals (r/sre, Blind, HackerNews)
- *"We have 5 years of post-mortems that nobody reads. They're write-only documents."* — **r/sre**
- *"The biggest productivity killer on my team isn't system complexity—it's institutional amnesia."* — **Blind (Infra Eng, Large Bank)**

---

## 3. Where the Process Breaks

### 3.1 Knowledge is Trapped in Silos
| Where Knowledge Lives | Access | Searchable? |
| :--- | :--- | :--- |
| **Email Threads** | Only CC'd individuals | No |
| **Slack DMs / Group Chats** | Participants only | Barely (noisy keyword search) |
| **Jira Comments** | Anyone with Jira access | Practically no (keyword mismatch) |
| **Confluence Runbooks** | Anyone with access | Yes, but rarely updated |
| **Senior Engineers' Heads** | When they are online | No |

### 3.2 Context ≠ Keywords
When an engineer searches Jira for *"PDF rendering timeout,"* they miss tickets describing the same root cause as *"statement generation batch job hung"* or *"renderer process killed."* Keyword search fails because **engineers describe problems by whichever symptom they observe first.**

### 3.3 Knowledge Decays on Rotation
Investment bank support teams rotate regularly. When a senior engineer leaves or rotates:
- Undocumented heuristics (*"this error usually means X"*) disappear.
- New members must re-discover failure modes from scratch.
- **Ramp-up time to reach 80% resolution speed takes 4–6 months.**

---

## 4. Jobs To Be Done (JTBD)

| Context | Job To Be Done | Desired Outcome |
| :--- | :--- | :--- |
| **On-call under time pressure** (2am P1/P2 alert) | I want to instantly know if this failure pattern has occurred before... | Resolve confidently in **<15 min** instead of 30–60 min searching. |
| **Post-resolution** (fresh debugging context) | I want to effortlessly capture the resolution and root cause... | Externalize knowledge into a searchable format without manual documentation overhead. |
| **New joiner onboarding** (first 3 months) | I want self-serve access to historical incident resolutions... | Resolve independent of senior engineer availability. |
| **Weekly review** (team lead / Monday morning) | I want to identify which incident patterns keep recurring... | Prioritize systemic engineering fixes over repeated firefighting. |

---

## 5. Opportunity Sizing

**Within a Single Team (Client Reporting, ~8 engineers):**
- **Volume:** ~50 incidents/month.
- **Current Waste:** 30–60 min search time/incident = **25–50 hours/month lost to searching.**
- **Impact:** Cutting search time by 50% saves **12–25 hours/month** (~2–3 engineer-days returned to problem-solving).

**Across an Investment Bank (10–15 Production Support Teams):**
- **Total Waste:** **150–750 hours/month** lost across all teams.
- **Validation:** Engineers currently build ad-hoc spreadsheets and personal notes to track past fixes—proving the pain is acute and existing tools (Jira/Confluence/Slack) are failing to solve it.
