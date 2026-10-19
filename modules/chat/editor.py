"""
Editor da pergunta: o QTextDocument de um TextArea da QML, com as fotos
embutidas no texto como imagens.

A ordem do que vai para a IA é a ordem visual: items() percorre o documento e
devolve trechos de texto e ids de blocos (fotos, espaços reservados) na
sequência em que aparecem. A edição funciona como em qualquer editor (cursor,
seleção, desfazer, colar), e a foto é só mais um caractere: ⌫ a apaga.

O editor não guarda estado próprio da pergunta. ChatSession.draft é a fonte
da verdade:
- a cada edição, items() vira session.replace_draft();
- quando a sessão muda o rascunho (foto, transcrição, rascunho devolvido após
  erro), rebuild() faz o documento refletir os blocos.

rebuild() é incremental: compara o conteúdo atual com o desejado por trechos e
só substitui o meio que mudou. O cursor e o texto que o aluno está digitando
ficam onde estavam.

Sem QML aqui: os testes usam um QTextDocument comum.
"""

from __future__ import annotations

from collections.abc import Iterator

from PySide6.QtCore import QSize
from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextDocument, QTextImageFormat

from modules.chat.session import DraftBlock
from ui import images

THUMB_PX = 72  # altura da miniatura no editor

Item = str | int  # trecho de texto ou id de bloco embutido (ver ChatSession.replace_draft)
Token = tuple[str, str]  # ("text", conteúdo) | ("chip", endereço da imagem)
_LINE_SEPARATOR = chr(0x2028)  # quebra de linha dentro do parágrafo (Shift+Enter)


class RichEditor:
    """Conteúdo de `document` ↔ blocos do rascunho.

    `prefix` distingue as imagens desta entrada no módulo no cache do Qt
    (ver ui/images.py); cada foto exibida é registrada lá.
    """

    def __init__(self, document: QTextDocument, prefix: str):
        self.document = document
        self._prefix = prefix
        self._ids: dict[str, int] = {}  # endereço da imagem → id do bloco
        self.rebuilding = False

    # ------------------------------------------------------------------ leitura

    def items(self, start: int = 0, end: int | None = None) -> list[Item]:
        """Conteúdo entre as posições `start` e `end`: texto e ids, na ordem."""
        end = self.length if end is None else end
        items: list[Item] = []
        buffer: list[str] = []
        for position, text, name in self._walk():
            if text is not None:
                piece = text[max(0, start - position) : max(0, end - position)]
                if piece:
                    buffer.append(piece)
            elif start <= position < end and name in self._ids:
                if buffer:
                    items.append("".join(buffer))
                    buffer = []
                items.append(self._ids[name])
        if buffer:
            items.append("".join(buffer))
        return items

    def split(self, position: int) -> tuple[list[Item], list[Item]]:
        """(antes, depois) da posição: onde entra uma foto ou uma fala nova."""
        return self.items(0, position), self.items(position)

    def block_at(self, position: int) -> int | None:
        """Id do bloco embutido na posição (o caractere logo depois dela)."""
        for at, text, name in self._walk():
            if text is None and at == position:
                return self._ids.get(name)
        return None

    @property
    def length(self) -> int:
        return max(0, self.document.characterCount() - 1)

    @property
    def is_empty(self) -> bool:
        return not any(name in self._ids or (text or "").strip() for _p, text, name in self._walk())

    # ------------------------------------------------------------------ escrita

    def rebuild(self, blocks: list[DraftBlock], focus_id: int | None = None) -> int | None:
        """Faz o documento refletir `blocks`.

        Retorna a posição logo depois do bloco `focus_id` (foto ou transcrição
        nova), onde a tela põe o cursor; None se não há foco pedido.
        """
        target = self._target(blocks)
        current = self._tokens()
        p = 0
        while p < min(len(current), len(target)) and current[p][0] == target[p][0]:
            p += 1
        q = 0
        while (
            q < min(len(current), len(target)) - p
            and current[len(current) - 1 - q][0] == target[len(target) - 1 - q][0]
        ):
            q += 1

        start = current[p][1] if p < len(current) else self.length
        end = current[len(current) - q][1] if q else self.length
        focus: int | None = None
        self.rebuilding = True
        try:
            cursor = QTextCursor(self.document)
            cursor.beginEditBlock()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            for token, image, ids in target[p : len(target) - q]:
                if token[0] == "text":
                    cursor.insertText(token[1], QTextCharFormat())
                else:
                    cursor.insertImage(image)
                if focus_id in ids:
                    focus = cursor.position()
            cursor.endEditBlock()
            # O desfazer não atravessa um redesenho feito pela sessão.
            self.document.clearUndoRedoStacks()
        finally:
            self.rebuilding = False
        self._ids = {token[1]: ids[0] for token, _img, ids in target if token[0] == "chip"}
        if focus is None and focus_id is not None:
            focus = self._after(focus_id)
        return focus

    def insert_plain(self, position: int, text: str) -> int:
        """Cola `text` sem formatação na posição; devolve a posição depois dele."""
        cursor = QTextCursor(self.document)
        cursor.setPosition(position)
        cursor.insertText(text, QTextCharFormat())
        return cursor.position()

    # ------------------------------------------------------------------ interno

    def _target(self, blocks: list[DraftBlock]) -> list[tuple[Token, object, list[int]]]:
        """Blocos → trechos do documento: (chave, formato da imagem, ids dos blocos).

        Textos vizinhos viram um trecho só (é o que o documento guarda); duas
        falas seguidas ganham um espaço entre elas para não grudarem.
        """
        items: list[tuple[Token, object, list[int]]] = []
        for block in blocks:
            if block.kind == "text" and block.pending is None:
                piece = block.text
                if items and items[-1][0][0] == "text":
                    previous = items[-1][0][1]
                    if piece and previous and not previous[-1].isspace() and not piece[0].isspace():
                        piece = " " + piece
                    items[-1] = (("text", previous + piece), None, items[-1][2] + [block.id])
                elif piece:
                    items.append((("text", piece), None, [block.id]))
                continue
            key = f"{self._prefix}{block.id}"
            if block.pending is not None or block.image is None:
                label = block.pending or block.label
                url, size = images.pending_url(key, label), images.pill_size(label)
            else:
                url = images.put(key, block.image.data)
                size = _thumb_size(block)
            image = QTextImageFormat()
            image.setName(url)
            image.setWidth(size.width())
            image.setHeight(size.height())
            image.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
            items.append((("chip", url), image, [block.id]))
        return items

    def _tokens(self) -> list[tuple[Token, int]]:
        """Conteúdo atual: (chave, posição de início) por trecho."""
        tokens: list[tuple[Token, int]] = []
        buffer: list[str] = []
        start = 0
        for position, text, name in self._walk():
            if text is not None:
                if not buffer:
                    start = position
                buffer.append(text)
                continue
            if buffer:
                tokens.append((("text", "".join(buffer)), start))
                buffer = []
            tokens.append((("chip", name), position))
        if buffer:
            tokens.append((("text", "".join(buffer)), start))
        return tokens

    def _after(self, block_id: int) -> int | None:
        """Posição logo depois da imagem do bloco (foco num bloco que não mudou)."""
        for position, text, name in self._walk():
            if text is None and self._ids.get(name) == block_id:
                return position + 1
        return None

    def _walk(self) -> Iterator[tuple[int, str | None, str | None]]:
        """(posição, texto, None) para trechos de texto e (posição, None, endereço)
        para cada imagem, na ordem do documento. Parágrafos viram "\\n"."""
        block = self.document.begin()
        first = True
        while block.isValid():
            if not first:
                yield block.position() - 1, "\n", None
            first = False
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isImageFormat():
                        name = fmt.toImageFormat().name()
                        for offset in range(fragment.length()):
                            yield fragment.position() + offset, None, name
                    else:
                        yield (
                            fragment.position(),
                            fragment.text().replace(_LINE_SEPARATOR, "\n"),
                            None,
                        )
                it += 1
            block = block.next()


def _thumb_size(block: DraftBlock) -> QSize:
    image = block.image
    if image is None or image.height <= 0:
        return QSize(THUMB_PX, THUMB_PX)
    width = round(THUMB_PX * image.width / image.height)
    return QSize(max(24, min(width, THUMB_PX * 2)), THUMB_PX)
