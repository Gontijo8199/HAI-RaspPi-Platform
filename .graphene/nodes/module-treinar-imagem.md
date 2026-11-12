---
type: module
summary: 'Treinar reconhecedor': classes + live webcam preview (LiveCamera, ~10 fps), MobileNetV2 ONNX embeddings + numpy KNN; + and Testar use the frame on screen, falling back to per-tap capture
entry_points:
  - modules/treinar_imagem/module.py
  - modules/treinar_imagem/controller.py
  - modules/treinar_imagem/logic.py
  - modules/treinar_imagem/embedder.py
covers:
  - modules/treinar_imagem/**
  - tests/test_treinar_imagem_*.py
last_commit: 4d1d2e3
edges:
  - to: vision-camera type: depends_on reason: captures each photo via services.camera.capture()
  - to: ui-images type: depends_on reason: shows last photo via images.put/drop
  - to: poc-html type: mirrors reason: port of treinar-imagem.html
---

- Model file models/mobilenetv2.onnx is gitignored; fetched by `python -m modules.treinar_imagem.embedder --download` from ONNX model zoo mobilenetv2-12 (input [N,3,224,224] NCHW float, output [N,1000] logits). Logits are used as the embedding (onnx package not installed, so no penultimate layer) — works on sanity checks. Dockerfile downloads it at build. onnxruntime comes transitively from faster-whisper but is now listed in requirements.txt. <!-- id:6a63 -->
- KNN gotcha: plain k=min(3,n) gives a permanent 50/50 tie with 1 photo per class (the POC's TF.js knn has this bug). logic.Classifier caps k at the smallest class size. <!-- id:6428 -->
- Controller must set busy synchronously in the slot (_start) before spawning; setting it inside the task let a fast double tap spawn two captures. Covered by test_toque_duplo_tira_uma_foto_so. <!-- id:e703 -->
- Live preview QML Image uses cache:false and synchronous load (async flickers between frames); each frame gets a new images key ending in '.' so drop(prefix) of the previous key can't match later ones ('…1.' vs '…10.'). Only the shown frame stays in ui.images. <!-- id:648d -->
