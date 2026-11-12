---
type: subsystem
summary: Config loading and shared services (LLM, TTS, camera, lazy Whisper) built once per run
entry_points:
  - core/services.py
  - config/settings.example.toml
covers:
  - core/services.py
  - config/**
last_commit: 4d1d2e3
edges:
  - to: api-llm type: related_to reason: build_llm creates LLMClient from [api] settings
---
