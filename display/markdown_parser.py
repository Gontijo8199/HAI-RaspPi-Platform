"""
Parser de Markdown, sem dependências externas.

Não tenta cobrir o spec completo do CommonMark, só o suficiente para o que
o LLM tipicamente devolve (respostas do tutor e flash-cards): headings,
**negrito**, *itálico*, código inline, blocos código, listas com
"-"/"*"/"1.", blockquotes ">" e linhas horizontais "---".

Mantido em um módulo separado (sem import tkinter) para poder ser testado
com pytest puro, mesmo em ambientes sem servidor X / sem Tk instalado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_INLINE_PATTERN = re.compile(r"(\*\*.+?\*\*|`.+?`|\*[^*\n]+?\*)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_HR_VALUES = {"---", "***", "___"}


@dataclass(frozen=True)
class Run:
    text: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Block:
    type: str
    runs: tuple[Run, ...] = field(default_factory=tuple)
    level: int | None = None
    index: str | None = None
    text: str = ""


def _parse_inline(text: str) -> tuple[Run, ...]:
    runs: list[Run] = []
    pos = 0
    for match in _INLINE_PATTERN.finditer(text):
        if match.start() > pos:
            runs.append(Run(text[pos : match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            runs.append(Run(token[2:-2], ("bold",)))
        elif token.startswith("`"):
            runs.append(Run(token[1:-1], ("code",)))
        else:  # itálico
            runs.append(Run(token[1:-1], ("italic",)))
        pos = match.end()
    if pos < len(text):
        runs.append(Run(text[pos:]))
    if not runs:
        runs.append(Run(""))
    return tuple(runs)


def parse_markdown(markdown_text: str) -> list[Block]:
    blocks: list[Block] = []
    in_code_block = False
    code_lines: list[str] = []

    for raw_line in (markdown_text or "").splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                blocks.append(Block(type="code_block", text="\n".join(code_lines)))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            blocks.append(Block(type="blank"))
            continue

        if stripped in _HR_VALUES:
            blocks.append(Block(type="hr"))
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            level = len(heading_match.group(1))
            blocks.append(
                Block(type="heading", level=level, runs=_parse_inline(heading_match.group(2)))
            )
            continue

        bullet_match = _BULLET_RE.match(stripped)
        if bullet_match:
            blocks.append(Block(type="bullet", runs=_parse_inline(bullet_match.group(1))))
            continue

        numbered_match = _NUMBERED_RE.match(stripped)
        if numbered_match:
            blocks.append(
                Block(
                    type="numbered",
                    index=numbered_match.group(1),
                    runs=_parse_inline(numbered_match.group(2)),
                )
            )
            continue

        quote_match = _QUOTE_RE.match(stripped)
        if quote_match:
            blocks.append(Block(type="quote", runs=_parse_inline(quote_match.group(1))))
            continue

        blocks.append(Block(type="paragraph", runs=_parse_inline(stripped)))

    if in_code_block and code_lines:
        blocks.append(Block(type="code_block", text="\n".join(code_lines)))

    return blocks
