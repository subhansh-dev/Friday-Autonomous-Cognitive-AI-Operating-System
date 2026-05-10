---
name: ai_pipeline
trigger: When the user wants to run an AI analysis pipeline on data
freedom: high
gotchas:
  - Large datasets may take time — use pagination
  - Results depend on data quality — garbage in, garbage out
  - API rate limits apply
---

pipeline_type: "sentiment", "classify", "summarize", "extract", "custom"
data: string or list — input text, file path, or JSON data
Returns: structured results with confidence scores
For custom: provide pipeline config with steps.