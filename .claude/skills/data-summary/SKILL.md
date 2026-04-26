---
name: data-summary
description: Read a CSV or JSON file and produce a structured data quality report — row count, nulls, data types, anomalies, and a 3-line summary of what the data contains.
allowed-tools: Bash(python *)
---

Analyzing `{{args}}`...

Use the Bash tool to run the following command, substituting `{{args}}` with the actual file path from args:

```bash
python .claude/skills/data-summary/analyze.py "{{args}}"
```

---

After the report above, write a **Summary** section with exactly 3 sentences:
1. What the dataset appears to represent (infer from column names and sample values).
2. Overall data quality — highlight the most important issues from the anomalies section, or confirm it looks clean.
3. One actionable observation: the most useful thing to investigate or clean before using this data.

Keep each sentence under 25 words.
