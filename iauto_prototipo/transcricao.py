"""Transcrição de fala em português com modelo ASR baseado em Transformer.

Usa o Whisper por meio da biblioteca faster-whisper, executado localmente na
CPU. O Whisper é um Transformer codificador-decodificador com mecanismo de
atenção, robusto a variações de sotaque e a ruídos de fundo, alinhado ao que
o projeto descreve para o módulo iAuto.
"""

_MODELO = None


def carregar_modelo(tamanho="small"):
    """Carrega o modelo ASR uma única vez (na primeira execução ele é baixado)."""
    global _MODELO
    if _MODELO is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as erro:
            raise ImportError(
                "A biblioteca faster-whisper não está instalada. "
                "Instale as dependências com: pip install -r requirements.txt"
            ) from erro
        print(f"[iAuto] Carregando modelo ASR ({tamanho})...")
        _MODELO = WhisperModel(tamanho, device="cpu", compute_type="int8")
    return _MODELO


def transcrever(caminho_audio, tamanho_modelo="small"):
    """Transcreve um arquivo de áudio (wav, mp3, ogg, opus, m4a) em PT-BR."""
    modelo = carregar_modelo(tamanho_modelo)
    segmentos, _info = modelo.transcribe(
        caminho_audio, language="pt", vad_filter=True
    )
    texto = " ".join(segmento.text.strip() for segmento in segmentos)
    return texto.strip()
