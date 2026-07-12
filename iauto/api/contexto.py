"""Contexto do processo: configuração ativa e sessões de entrevista em memória.

O par vaga/candidato ativo e o tamanho do modelo ASR valem para o processo
inteiro (adequado ao protótipo de fluxo único da entrevista web); as rotas
sem estado de ``rotas_pipeline`` não dependem deste módulo.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from iauto.dominio.modelos import Candidato, Pergunta, Resposta, Vaga
from iauto.servicos.transcricao import escolher_modelo

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
CAMINHO_INDEX = RAIZ_PROJETO / "web" / "index.html"
PASTA_DADOS = RAIZ_PROJETO / "dados"
PASTA_SAIDA = RAIZ_PROJETO / "saida"


@dataclass
class Sessao:
    vaga: Vaga
    candidato: Candidato
    roteiro: list[Pergunta]
    pasta: str
    respostas: dict[int, Resposta] = field(default_factory=dict)
    finalizada: dict | None = None


@dataclass
class Contexto:
    vaga: Vaga | None = None
    candidato: Candidato | None = None
    modelo: str = "tiny"
    sessoes: dict[str, Sessao] = field(default_factory=dict)

    def configurar(
        self,
        caminho_vaga: str | None = None,
        caminho_candidato: str | None = None,
        modelo: str = "auto",
    ) -> None:
        self.vaga = _carregar(Vaga, caminho_vaga or PASTA_DADOS / "vaga_exemplo.json")
        self.candidato = _carregar(
            Candidato, caminho_candidato or PASTA_DADOS / "candidato_exemplo.json"
        )
        self.modelo = escolher_modelo() if modelo == "auto" else modelo

    def garantir_configuracao(self) -> None:
        """Carrega a configuração padrão na primeira necessidade (lazy)."""
        if self.vaga is None or self.candidato is None:
            self.configurar()


def _carregar(tipo, caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return tipo.model_validate(json.load(arquivo))


contexto = Contexto()
