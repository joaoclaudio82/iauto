"""Corpos de requisição das rotas do pipeline, compostos dos modelos de domínio."""

from pydantic import BaseModel

from iauto.dominio.modelos import Analise, Candidato, Resposta, Vaga


class RoteiroRequisicao(BaseModel):
    vaga: Vaga
    candidato: Candidato


class AnaliseRequisicao(BaseModel):
    vaga: Vaga
    respostas: list[Resposta]


class RelatorioRequisicao(BaseModel):
    vaga: Vaga
    candidato: Candidato
    respostas: list[Resposta]
    analise: Analise
