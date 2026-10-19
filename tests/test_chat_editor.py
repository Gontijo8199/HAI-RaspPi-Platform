"""Editor da pergunta (modules/chat/editor.py) sobre um QTextDocument, sem QML."""

import pytest
from fakes import _image
from PySide6.QtGui import QTextCursor, QTextDocument

from modules.chat.editor import RichEditor
from modules.chat.session import DraftBlock
from ui import images


@pytest.fixture
def editor(qapp):
    document = QTextDocument()
    yield RichEditor(document, "t-")
    images.drop("t-")


def text(block_id, value):
    return DraftBlock(block_id, "text", text=value)


def photo(block_id, n=1):
    return DraftBlock(block_id, "photo", image=_image(n), label=f"foto {n}")


def type_at(editor, position, value):
    cursor = QTextCursor(editor.document)
    cursor.setPosition(position)
    cursor.insertText(value)


def images_in(editor):
    out = []
    block = editor.document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fmt = it.fragment().charFormat()
            if fmt.isImageFormat():
                out.append(fmt.toImageFormat().name())
            it += 1
        block = block.next()
    return out


def test_serializa_texto_e_fotos_na_ordem_visual(editor):
    focus = editor.rebuild([text(1, "olha "), photo(2), text(3, " e isto\nsegunda linha")], 2)
    assert editor.items() == ["olha ", 2, " e isto\nsegunda linha"]
    assert focus == 6  # logo depois da foto
    assert editor.block_at(5) == 2
    assert images.stored() == 1  # o JPEG foi registrado para a QML


def test_dividir_no_cursor(editor):
    editor.rebuild([text(1, "antes"), photo(2), text(3, "depois")])
    assert editor.split(3) == (["ant"], ["es", 2, "depois"])
    assert editor.split(editor.length) == (["antes", 2, "depois"], [])


def test_digitar_depois_da_foto_e_texto_comum(editor):
    editor.rebuild([text(1, "a"), photo(2)])
    type_at(editor, editor.length, "bc")
    assert editor.items() == ["a", 2, "bc"]


def test_apagar_a_foto_como_um_caractere(editor):
    editor.rebuild([text(1, "a"), photo(2), text(3, "b")])
    cursor = QTextCursor(editor.document)
    cursor.setPosition(2)
    cursor.deletePreviousChar()  # ⌫ logo depois da foto
    assert editor.items() == ["ab"]


def test_espaco_reservado_vira_conteudo_sem_mexer_no_resto(editor):
    first, second = photo(2, 1), photo(4, 2)
    editor.rebuild([text(1, "a "), first, text(3, " b "), second])
    antes = images_in(editor)

    gravando = DraftBlock(9, "text", pending="gravando…")
    editor.rebuild([text(1, "a "), first, text(3, " b "), second, gravando])
    assert editor.items() == ["a ", 2, " b ", 4, 9]
    assert images_in(editor)[:2] == antes  # as fotos que já estavam não foram refeitas

    gravando.pending, gravando.text = None, "quanto é dois mais dois"
    focus = editor.rebuild([text(1, "a "), first, text(3, " b "), second, gravando], 9)
    assert editor.items() == ["a ", 2, " b ", 4, "quanto é dois mais dois"]
    assert focus == editor.length


def test_rebuild_preserva_o_que_o_aluno_digitou_fora_do_trecho_mudado(editor):
    editor.rebuild([text(1, "começo "), photo(2)])
    type_at(editor, 0, ">> ")
    blocks = [text(1, ">> começo "), photo(2), DraftBlock(5, "photo", pending="tirando foto…")]
    editor.rebuild(blocks)
    assert editor.items() == [">> começo ", 2, 5]


def test_falas_seguidas_nao_grudam(editor):
    editor.rebuild([text(1, "primeira"), text(2, "segunda")])
    assert editor.items() == ["primeira segunda"]


def test_vazio_e_colar_sem_formatacao(editor):
    assert editor.is_empty
    editor.rebuild([DraftBlock(1, "text", pending="gravando…")])
    assert not editor.is_empty  # o espaço reservado conta
    editor.rebuild([])
    assert editor.is_empty
    end = editor.insert_plain(0, "colado\n<b>sem negrito</b>")
    assert editor.items() == ["colado\n<b>sem negrito</b>"]
    assert end == editor.length
