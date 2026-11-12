---
type: subsystem
summary: google-genai wrapper: streaming chat (send_parts_stream) and generate_image; errors -> LLMError via describe_error
entry_points:
  - api/llm_client.py
covers:
  - api/**
last_commit: 4d1d2e3
edges:
  - to: core-services type: related_to reason: build_llm creates LLMClient from [api] settings
---
