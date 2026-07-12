"""Testes do serviço de transcrição (iauto.servicos.transcricao).

Nenhum teste baixa ou carrega o Whisper de verdade: o carregamento do modelo
é substituído por dublês com monkeypatch e o cache local do Hugging Face é
simulado com tmp_path.
"""

import pytest

from iauto.servicos import transcricao
from iauto.servicos.transcricao import AsrOcupadoErro, escolher_modelo, transcrever


class _SegmentoFalso:
    """Imita um segmento do faster-whisper: só precisa do atributo .text."""

    def __init__(self, text: str):
        self.text = text


class _ModeloFalso:
    """Imita um WhisperModel: transcribe devolve (iterável de segmentos, info)."""

    def __init__(self, textos):
        self._textos = textos
        self.chamadas = []

    def transcribe(self, caminho_audio, **kwargs):
        self.chamadas.append((caminho_audio, kwargs))
        return iter(_SegmentoFalso(texto) for texto in self._textos), None


class _ModeloQueFalha:
    def transcribe(self, caminho_audio, **kwargs):
        raise RuntimeError("falha simulada na inferência")


# ---------------------------------------------------------------------------
# escolher_modelo
# ---------------------------------------------------------------------------


def test_escolher_modelo_sem_cache_devolve_reserva(tmp_path, monkeypatch):
    """Com HF_HOME apontando para um cache vazio, cai no modelo reserva."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert escolher_modelo(preferido="small", reserva="tiny") == "tiny"


def test_escolher_modelo_com_cache_devolve_preferido(tmp_path, monkeypatch):
    """Se o model.bin do preferido já está no cache local, usa o preferido."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    snapshot = tmp_path / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "x"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"")
    assert escolher_modelo(preferido="small", reserva="tiny") == "small"


def test_escolher_modelo_ignora_cache_de_outro_tamanho(tmp_path, monkeypatch):
    """Cache do tiny não conta como cache do small."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    snapshot = tmp_path / "hub" / "models--Systran--faster-whisper-tiny" / "snapshots" / "y"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"")
    assert escolher_modelo(preferido="small", reserva="tiny") == "tiny"


# ---------------------------------------------------------------------------
# transcrever
# ---------------------------------------------------------------------------


def test_transcrever_ocupado_levanta_asr_ocupado():
    """Se a trava do tamanho já está tomada, responde AsrOcupadoErro sem esperar."""
    tamanho = "teste-trava-ocupada"
    trava = transcricao._trava_do(tamanho)
    assert trava.acquire(timeout=0)
    try:
        with pytest.raises(AsrOcupadoErro):
            transcrever("qualquer.wav", tamanho_modelo=tamanho, tempo_espera=0)
    finally:
        trava.release()


def test_transcrever_junta_e_limpa_os_segmentos(monkeypatch):
    """O texto final é a junção dos segmentos, sem espaços sobrando nas pontas."""
    tamanho = "teste-modelo-falso"
    modelo = _ModeloFalso(["  Olá, tudo bem?  ", " Eu trabalho com Python. "])
    monkeypatch.setattr(transcricao, "_carregar_sem_trava", lambda _tamanho: modelo)

    texto = transcrever("entrevista.wav", tamanho_modelo=tamanho, tempo_espera=1)

    assert texto == "Olá, tudo bem? Eu trabalho com Python."


def test_transcrever_pede_portugues_com_filtro_de_voz(monkeypatch):
    """A inferência deve ser chamada com language=pt e vad_filter ligado."""
    tamanho = "teste-parametros"
    modelo = _ModeloFalso(["oi"])
    monkeypatch.setattr(transcricao, "_carregar_sem_trava", lambda _tamanho: modelo)

    transcrever("audio.ogg", tamanho_modelo=tamanho, tempo_espera=1)

    caminho, kwargs = modelo.chamadas[0]
    assert caminho == "audio.ogg"
    assert kwargs["language"] == "pt"
    assert kwargs["vad_filter"] is True


def test_transcrever_libera_a_trava_apos_sucesso(monkeypatch):
    """Duas transcrições seguidas do mesmo tamanho funcionam (trava liberada)."""
    tamanho = "teste-trava-liberada"
    modelo = _ModeloFalso(["primeira"])
    monkeypatch.setattr(transcricao, "_carregar_sem_trava", lambda _tamanho: modelo)

    assert transcrever("a.wav", tamanho_modelo=tamanho, tempo_espera=1) == "primeira"
    assert transcrever("b.wav", tamanho_modelo=tamanho, tempo_espera=1) == "primeira"


def test_transcrever_libera_a_trava_apos_erro(monkeypatch):
    """Mesmo quando a inferência falha, a trava do tamanho não fica presa."""
    tamanho = "teste-trava-apos-erro"
    monkeypatch.setattr(transcricao, "_carregar_sem_trava", lambda _tamanho: _ModeloQueFalha())

    with pytest.raises(RuntimeError):
        transcrever("c.wav", tamanho_modelo=tamanho, tempo_espera=1)

    trava = transcricao._trava_do(tamanho)
    assert trava.acquire(timeout=0)
    trava.release()
