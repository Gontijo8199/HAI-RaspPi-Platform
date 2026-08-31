from display.markdown_display import MarkdownDisplay
from display.markdown_parser import parse_markdown


class TestParseMarkdown:
    def test_heading(self):
        blocks = parse_markdown("## Fotossíntese")
        assert len(blocks) == 1
        assert blocks[0].type == "heading"
        assert blocks[0].level == 2
        assert blocks[0].runs[0].text == "Fotossíntese"

    def test_bold_and_italic_inline(self):
        blocks = parse_markdown("Isso é **importante** e isso é *sutil*.")
        assert len(blocks) == 1
        runs = blocks[0].runs
        bold_runs = [r for r in runs if "bold" in r.tags]
        italic_runs = [r for r in runs if "italic" in r.tags]
        assert bold_runs[0].text == "importante"
        assert italic_runs[0].text == "sutil"

    def test_inline_code(self):
        blocks = parse_markdown("Use `print()` para imprimir.")
        code_runs = [r for r in blocks[0].runs if "code" in r.tags]
        assert code_runs[0].text == "print()"

    def test_bullet_list(self):
        blocks = parse_markdown("- item um\n- item dois")
        assert [b.type for b in blocks] == ["bullet", "bullet"]
        assert blocks[0].runs[0].text == "item um"
        assert blocks[1].runs[0].text == "item dois"

    def test_numbered_list(self):
        blocks = parse_markdown("1. primeiro\n2. segundo")
        assert blocks[0].type == "numbered"
        assert blocks[0].index == "1"
        assert blocks[1].index == "2"

    def test_blockquote(self):
        blocks = parse_markdown("> uma citação")
        assert blocks[0].type == "quote"
        assert blocks[0].runs[0].text == "uma citação"

    def test_horizontal_rule(self):
        blocks = parse_markdown("---")
        assert blocks[0].type == "hr"

    def test_code_block(self):
        blocks = parse_markdown("```\nx = 1\ny = 2\n```")
        assert len(blocks) == 1
        assert blocks[0].type == "code_block"
        assert blocks[0].text == "x = 1\ny = 2"

    def test_code_block_sem_fechamento_nao_quebra(self):
        blocks = parse_markdown("```\nx = 1")
        assert blocks[-1].type == "code_block"
        assert blocks[-1].text == "x = 1"

    def test_blank_line_preservada(self):
        blocks = parse_markdown("linha 1\n\nlinha 2")
        assert [b.type for b in blocks] == ["paragraph", "blank", "paragraph"]

    def test_paragraph_simples(self):
        blocks = parse_markdown("Texto simples sem formatação.")
        assert blocks[0].type == "paragraph"
        assert blocks[0].runs[0].text == "Texto simples sem formatação."

    def test_texto_vazio(self):
        assert parse_markdown("") == []

    def test_flashcard_completo(self):
        markdown_text = (
            "## Fotossíntese\n"
            "**Resumo:** processo pelo qual plantas convertem luz em energia.\n"
            "- ocorre nos cloroplastos\n"
            "- libera oxigênio\n"
        )
        blocks = parse_markdown(markdown_text)
        types = [b.type for b in blocks]
        assert types[0] == "heading"
        assert types[1] == "paragraph"
        assert "bullet" in types


class TestMarkdownDisplayHeadless:
    def test_inicializa_sem_lancar_excecao(self):
        display = MarkdownDisplay(headless=True)
        try:
            assert display.available is False
        finally:
            display.shutdown()

    def test_show_response_nao_bloqueia_nem_lanca(self):
        display = MarkdownDisplay(headless=True)
        try:
            display.show_response("## Título\nConteúdo qualquer.")
        finally:
            display.shutdown()

    def test_show_flashcard_nao_bloqueia_nem_lanca(self):
        display = MarkdownDisplay(headless=True)
        try:
            display.show_flashcard("## Tópico\n**Resumo:** teste.")
        finally:
            display.shutdown()

    def test_clear_nao_lanca(self):
        display = MarkdownDisplay(headless=True)
        try:
            display.clear()
        finally:
            display.shutdown()

    def test_show_status_nao_lanca(self):
        display = MarkdownDisplay(headless=True)
        try:
            display.show_status("Ouvindo...")
        finally:
            display.shutdown()

    def test_shutdown_e_idempotente_o_suficiente(self):
        display = MarkdownDisplay(headless=True)
        display.shutdown()
        display.shutdown()
