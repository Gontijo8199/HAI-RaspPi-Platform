---
type: module
summary: 'Gerar imagem': prompt -> Gemini image via LLMClient.generate_image; image kept only in memory
entry_points:
  - modules/gerar_imagem/module.py
  - modules/gerar_imagem/controller.py
covers:
  - modules/gerar_imagem/**
  - tests/test_gerar_imagem_controller.py
last_commit: 4d1d2e3
edges:
  - to: api-llm type: depends_on reason: LLMClient.generate_image
  - to: ui-images type: depends_on reason: shows generated image
  - to: poc-html type: mirrors reason: port of gerar-imagem.html
---

- Image model from [api] image_model (default gemini-2.5-flash-image, unverified against the project key). generate_image uses client.aio so exit() cancellation cancels the request; timeout IMAGE_TIMEOUT_S=120 (timeout_s is per stream chunk). The POC Save button was intentionally dropped (nothing written to disk). <!-- id:26cb -->
