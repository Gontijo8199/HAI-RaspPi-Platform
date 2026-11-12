---
type: reference
summary: Untracked browser POC (HTML 'quadradinhos') that new modules are ported from; contains secrets
entry_points:
  - POC/interface/interface/README.md
covers:
  - POC/**
last_commit: 4d1d2e3
edges:
  - to: module-treinar-imagem type: mirrors reason: port of treinar-imagem.html
  - to: module-gerar-imagem type: mirrors reason: port of gerar-imagem.html
---

- POC/ contains a live Gemini key (config.js) and a TLS private key (cert/chave.pem). Never stage POC/; .dockerignore excludes POC/ so `COPY . .` doesn't bake them into the image. ruff check must use --exclude POC (macOS ._ files break it). <!-- id:d5ad -->
