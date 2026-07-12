"""Voz neural do entrevistador (vozes Microsoft, via edge-tts).

O frontend usa este serviço como primeira opção e cai para a voz do navegador
quando ele está indisponível — a entrevista nunca depende dele para avançar.
"""

import os

VOZ_PADRAO = os.environ.get("VOZ_TTS", "pt-BR-FranciscaNeural")
TAMANHO_MAXIMO = 600

_cache: dict[tuple[str, str], bytes] = {}


class TextoInvalidoErro(ValueError):
    """Texto vazio ou longo demais para sintetizar."""


async def sintetizar(texto: str, voz: str = VOZ_PADRAO) -> bytes:
    """Sintetiza o texto em MP3, com cache em memória por (voz, texto)."""
    texto = (texto or "").strip()
    if not texto or len(texto) > TAMANHO_MAXIMO:
        raise TextoInvalidoErro("Texto vazio ou longo demais para sintetizar.")

    chave = (voz, texto)
    if chave not in _cache:
        import edge_tts

        partes = []
        async for pedaco in edge_tts.Communicate(texto, voz).stream():
            if pedaco["type"] == "audio":
                partes.append(pedaco["data"])
        audio = b"".join(partes)
        if not audio:
            raise RuntimeError("o serviço de voz devolveu áudio vazio")
        _cache[chave] = audio
    return _cache[chave]
