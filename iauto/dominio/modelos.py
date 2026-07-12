"""Modelos de domínio do iAuto.

Fonte única de verdade para os dados que circulam entre as camadas: os
arquivos de ``dados/``, as rotas da API e o CLI validam contra estes modelos.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

TipoPergunta = Literal["abertura", "competencia", "situacional", "encerramento"]
Situacao = Literal["aderente", "parcial", "lacuna"]
MetodoAnalise = Literal["heuristico", "llm"]


class Competencia(BaseModel):
    nome: str
    peso: int = 1
    palavras_chave: list[str] = Field(default_factory=list)


class Vaga(BaseModel):
    titulo: str
    empresa: str = ""
    descricao: str = ""
    competencias: list[Competencia] = Field(default_factory=list)


class Candidato(BaseModel):
    nome: str
    resumo: str = ""
    experiencias: list[str] = Field(default_factory=list)

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("o nome do candidato não pode ser vazio")
        return valor


class Pergunta(BaseModel):
    id: int
    tipo: TipoPergunta
    competencia: str | None = None
    pergunta: str
    tempo_max: int = 90


class Resposta(Pergunta):
    """Uma pergunta do roteiro acompanhada da resposta transcrita."""

    resposta: str = ""
    arquivo_audio: str | None = None


class AvaliacaoCompetencia(BaseModel):
    competencia: str
    peso: int
    nota: int = Field(ge=0, le=100)
    situacao: Situacao
    termos_identificados: list[str] = Field(default_factory=list)
    trechos_relevantes: list[str] = Field(default_factory=list)
    tem_exemplo: bool = False
    n_palavras: int = 0
    riscos: list[str] = Field(default_factory=list)


class Analise(BaseModel):
    nota_geral: int = Field(ge=0, le=100)
    recomendacao: str
    avaliacoes: list[AvaliacaoCompetencia] = Field(default_factory=list)
    destaques: list[str] = Field(default_factory=list)
    riscos: list[str] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)
    metodo: MetodoAnalise = "heuristico"
    modelo_llm: str | None = None
