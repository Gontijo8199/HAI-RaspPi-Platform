---
type: subsystem
summary: Module contract (modules/base.py) and REGISTRY of menu modules with default on/off state
entry_points:
  - modules/__init__.py
  - modules/base.py
covers:
  - modules/__init__.py
  - modules/base.py
last_commit: 4d1d2e3
---

- QML gotcha in module pages: a ColumnLayout inherits Layout.fillWidth=true from any child that has it, so a fixed-width side column must set `Layout.fillWidth: false` or it eats the sibling's width (seen as negative width on the image pane). <!-- id:e449 -->
- Test gotcha: qthelpers.find() returns None for invisible items, and until() does not catch exceptions — predicates must null-check, e.g. `(r := find(w, 'x')) is not None and ...`. QQuickImage 'status' has no Python converter; use paintedWidth > 0 to detect a loaded image. <!-- id:77fe -->
