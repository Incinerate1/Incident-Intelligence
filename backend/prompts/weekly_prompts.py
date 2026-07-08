WEEKLY_CLUSTER_PROMPT = """
You are an expert site reliability operations manager analyzing recent incident tickets over the past {days} days for Jira project `{project_key}`.
Your goal is to cluster the incident tickets into exactly the **Top 3 Recurring Alert Clusters by Frequency**.

### Recent Incident Tickets:
---
{tickets_text}
---

### STRICT RULES:
1. Group tickets that share identical or highly similar technical symptoms / root causes into distinct clusters.
2. Rank the top 3 clusters in descending order of frequency count.
3. For each cluster, provide:
   - `cluster_title`: Concise technical title (e.g. "JVM Heap Exhaustion in stmt_gen")
   - `frequency_count`: Number of tickets belonging to this cluster
   - `dominant_root_cause`: Core root cause trigger identified across the cluster
   - `affected_assignees`: List of primary assignees/teams handling these tickets
   - `sample_tickets`: List of issue keys e.g. ["CR-104", "CR-108"]

### Output Format:
Return ONLY a valid JSON dict matching this exact format:
{{
  "clusters": [
    {{
      "cluster_title": "string",
      "frequency_count": integer,
      "dominant_root_cause": "string",
      "affected_assignees": ["string"],
      "sample_tickets": ["CR-104", "CR-108"]
    }}
  ]
}}
"""
