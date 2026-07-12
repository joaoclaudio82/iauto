"""iAuto — entrevista de emprego automatizada por áudio, em português.

Pacote organizado em três camadas:

- ``iauto.dominio``: regras de negócio puras (roteiro, análise, relatório)
  sobre modelos tipados, sem I/O.
- ``iauto.servicos``: adaptadores de infraestrutura (ASR local, LLM via
  OpenRouter, voz neural).
- ``iauto.api`` / ``iauto.cli``: pontos de entrada (servidor FastAPI e
  entrevista pelo terminal).
"""

__version__ = "0.2.0"
