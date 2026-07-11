"""Transcrição de fala em português com modelo ASR baseado em Transformer.

Usa o Whisper por meio da biblioteca faster-whisper, executado localmente na
CPU. O Whisper é um Transformer codificador-decodificador com mecanismo de
atenção, robusto a variações de sotaque e a ruídos de fundo, alinhado ao que
o projeto descreve para o módulo iAuto.
"""

import os
import threading

_MODELOS = {}
# Uma trava por tamanho de modelo: o download/carga de um tamanho novo não
# bloqueia transcrições com um modelo já carregado. A trava global curta só
# protege a criação das travas e o despejo do cache.
_TRAVAS = {}
_TRAVA_GLOBAL = threading.Lock()


class AsrOcupadoErro(RuntimeError):
    """O ASR está ocupado além do tempo de espera; o chamador deve responder 503."""


def _trava_do(tamanho):
    with _TRAVA_GLOBAL:
        return _TRAVAS.setdefault(tamanho, threading.Lock())


def escolher_modelo(preferido="small", reserva="tiny"):
    """Usa o modelo preferido se já estiver no cache local; senão, o reserva."""
    base = os.environ.get(
        "HF_HOME", os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    )
    pasta = os.path.join(base, "hub", f"models--Systran--faster-whisper-{preferido}")
    for _raiz, _dirs, arquivos in os.walk(pasta):
        if "model.bin" in arquivos:
            return preferido
    return reserva


def _carregar_sem_trava(tamanho):
    if tamanho not in _MODELOS:
        try:
            from faster_whisper import WhisperModel
        except ImportError as erro:
            raise ImportError(
                "A biblioteca faster-whisper não está instalada. "
                "Instale as dependências com: pip install -r requirements.txt"
            ) from erro
        print(f"[iAuto] Carregando modelo ASR ({tamanho})...")
        modelo = WhisperModel(tamanho, device="cpu", compute_type="int8")
        with _TRAVA_GLOBAL:
            # mantém um único tamanho na RAM (cada Whisper ocupa centenas de MB)
            for chave in list(_MODELOS):
                if chave != tamanho:
                    del _MODELOS[chave]
            _MODELOS[tamanho] = modelo
    return _MODELOS[tamanho]


def carregar_modelo(tamanho="small"):
    """Carrega o modelo ASR do tamanho pedido (na 1ª execução ele é baixado)."""
    with _trava_do(tamanho):
        return _carregar_sem_trava(tamanho)


def transcrever(caminho_audio, tamanho_modelo="small", tempo_espera=120):
    """Transcreve um arquivo de áudio (wav, mp3, ogg, opus, m4a, webm) em PT-BR.

    A inferência é serializada por tamanho de modelo; se a fila não andar em
    `tempo_espera` segundos, levanta AsrOcupadoErro em vez de segurar a thread
    indefinidamente.
    """
    trava = _trava_do(tamanho_modelo)
    if not trava.acquire(timeout=tempo_espera):
        raise AsrOcupadoErro(
            "O serviço de transcrição está ocupado; tente novamente em instantes."
        )
    try:
        modelo = _carregar_sem_trava(tamanho_modelo)
        segmentos, _info = modelo.transcribe(
            caminho_audio, language="pt", vad_filter=True
        )
        texto = " ".join(segmento.text.strip() for segmento in segmentos)
    finally:
        trava.release()
    return texto.strip()
