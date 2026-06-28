from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@patch("torch.hub.load")
def test_is_speech_acima_do_limiar(mock_hub):
    mock_model = MagicMock()
    mock_model.return_value.item.return_value = 0.9
    mock_hub.return_value = (mock_model, MagicMock())

    from stt.vad import SileroVAD

    vad = SileroVAD(threshold=0.5)
    chunk = np.zeros(512, dtype=np.int16).tobytes()
    is_speech, prob = vad.is_speech(chunk)

    assert is_speech is True
    assert prob == pytest.approx(0.9)


@patch("torch.hub.load")
def test_is_speech_abaixo_do_limiar(mock_hub):
    mock_model = MagicMock()
    mock_model.return_value.item.return_value = 0.2
    mock_hub.return_value = (mock_model, MagicMock())

    from stt.vad import SileroVAD

    vad = SileroVAD(threshold=0.5)
    chunk = np.zeros(512, dtype=np.int16).tobytes()
    is_speech, prob = vad.is_speech(chunk)

    assert is_speech is False
    assert prob == pytest.approx(0.2)


@patch("torch.hub.load")
def test_is_speech_exatamente_no_limiar(mock_hub):
    mock_model = MagicMock()
    mock_model.return_value.item.return_value = 0.5
    mock_hub.return_value = (mock_model, MagicMock())

    from stt.vad import SileroVAD

    vad = SileroVAD(threshold=0.5)
    chunk = np.zeros(512, dtype=np.int16).tobytes()
    is_speech, prob = vad.is_speech(chunk)

    assert is_speech is True


@patch("torch.hub.load")
def test_sample_rate_invalido(mock_hub):
    mock_hub.return_value = (MagicMock(), MagicMock())

    from stt.vad import SileroVAD

    with pytest.raises(ValueError):
        SileroVAD(sample_rate=8000)


@patch("torch.hub.load")
def test_reset_state_chamado(mock_hub):
    mock_model = MagicMock()
    mock_hub.return_value = (mock_model, MagicMock())

    from stt.vad import SileroVAD

    vad = SileroVAD()
    vad.reset_state()

    mock_model.reset_states.assert_called_once()
