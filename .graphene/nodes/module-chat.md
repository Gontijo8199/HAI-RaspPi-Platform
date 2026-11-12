---
type: module
summary: 'Conversar com a IA': text/voice/photo chat with remote LLM and TTS
entry_points:
  - modules/chat/module.py
  - modules/chat/session.py
  - modules/chat/controller.py
covers:
  - modules/chat/**
last_commit: 4d1d2e3
edges:
  - to: api-llm type: depends_on reason: streaming chat
---
