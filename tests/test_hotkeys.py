import asyncio
import sys

import pytest

from core.hotkeys import HotkeyListener, normalize_key, parse_key, pretty_key


class TestNormalizeKey:
    def test_esc_puro(self):
        assert normalize_key(b"\x1b") == "esc"

    def test_espaco(self):
        assert normalize_key(b" ") == "space"

    @pytest.mark.parametrize(
        "seq,name",
        [
            (b"\x1b[A", "up"),
            (b"\x1b[B", "down"),
            (b"\x1b[C", "right"),
            (b"\x1b[D", "left"),
        ],
    )
    def test_setas(self, seq, name):
        assert normalize_key(seq) == name

    @pytest.mark.parametrize("byte", [b"\r", b"\n"])
    def test_enter(self, byte):
        assert normalize_key(byte) == "enter"

    def test_ctrl_c(self):
        assert normalize_key(b"\x03") == "ctrl+c"

    def test_letra_minuscula(self):
        assert normalize_key(b"a") == "a"

    def test_maiuscula_normalizada(self):
        assert normalize_key(b"A") == "a"

    def test_utf8_acento(self):
        assert normalize_key("ç".encode()) == "ç"

    def test_sequencia_escape_desconhecida_ignorada(self):
        assert normalize_key(b"\x1b[1;2A") is None

    def test_byte_vazio(self):
        assert normalize_key(b"") is None

    def test_controle_nao_mapeado(self):
        assert normalize_key(b"\x01") is None


class TestParseKey:
    def test_apelidos_canonicos(self):
        assert parse_key("space") == "space"
        assert parse_key("espaco") == "space"
        assert parse_key("ESPAÇO") == "space"
        assert parse_key("escape") == "esc"
        assert parse_key("ctrl+c") == "ctrl+c"

    def test_letra_solta(self):
        assert parse_key("c") == "c"
        assert parse_key("X") == "x"

    def test_desconhecida_lanca(self):
        import pytest

        with pytest.raises(ValueError):
            parse_key("f13")

    def test_pretty_para_exibicao(self):
        assert pretty_key("space") == "Espaço"
        assert pretty_key("esc") == "Esc"
        assert pretty_key("c") == "C"


class TestHotkeyListenerDegracao:
    async def test_start_sem_tty_e_noop(self, monkeypatch):
        """Sem TTY (CI, pipes), o listener fica indisponível sem lançar erro."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        hotkeys = HotkeyListener()
        try:
            await hotkeys.start()
            assert hotkeys.available is False
        finally:
            hotkeys.stop()

    async def test_get_key_sem_start_pode_ser_cancelada(self):
        """Sem TTY, get_key não retorna — mas cancelar a task é seguro."""
        hotkeys = HotkeyListener()
        task = asyncio.get_running_loop().create_task(hotkeys.get_key())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestFilaDeTeclas:
    async def test_clear_descarta_teclas_bufferizadas(self):
        hotkeys = HotkeyListener()
        for key in ("esc", "enter", "a"):
            hotkeys._queue.put_nowait(key)
        hotkeys.clear()
        assert hotkeys._queue.empty()
