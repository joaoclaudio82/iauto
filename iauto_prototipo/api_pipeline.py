"""Rotas atômicas do pipeline iAuto, para consumo por outros backends.

Diferente do fluxo de sessão da entrevista web (servidor.py), estas rotas são
SEM ESTADO: cada chamada recebe todos os dados de que precisa (vaga, candidato,
respostas) e devolve o resultado, sem guardar nada em memória nem em disco.
Pensadas para um sistema de registro externo (por exemplo, um backend Spring)
que é o dono dos dados e chama este serviço internamente.

Documentação interativa em /docs (Swagger) e contrato em /openapi.json.
"""

import os
import shutil
import tempfile
from collections import Counter
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, field_validator

from analise_llm import analisar_com_fallback
from relatorio import montar_relatorio
from roteiro import gerar_roteiro
from transcricao import AsrOcupadoErro, escolher_modelo, transcrever

router = APIRouter(prefix="/api/v1", tags=["pipeline"])

TAMANHOS_ASR = ("tiny", "base", "small", "medium")


class Competencia(BaseModel):
    nome: str
    peso: int = 1
    palavras_chave: list[str] = []


class Vaga(BaseModel):
    titulo: str
    empresa: str = ""
    descricao: str = ""
    competencias: list[Competencia] = []


class Candidato(BaseModel):
    nome: str
    resumo: str = ""
    experiencias: list[str] = []

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("o nome do candidato não pode ser vazio")
        return valor


class RespostaItem(BaseModel):
    id: int
    tipo: str  # abertura | competencia | situacional | encerramento
    competencia: Optional[str] = None
    pergunta: str = ""
    tempo_max: int = 90
    resposta: str = ""


class Avaliacao(BaseModel):
    # extra="allow" preserva campos adicionais (tem_exemplo, n_palavras, riscos...)
    # para o round-trip /analise -> /relatorio não perder nada.
    model_config = ConfigDict(extra="allow")

    competencia: str
    peso: int = 1
    nota: float
    situacao: str
    termos_identificados: list[str] = []
    trechos_relevantes: list[str] = []


class Analise(BaseModel):
    model_config = ConfigDict(extra="allow")

    nota_geral: float
    recomendacao: str
    avaliacoes: list[Avaliacao] = []
    destaques: list[str] = []
    riscos: list[str] = []
    lacunas: list[str] = []


class RoteiroRequisicao(BaseModel):
    vaga: Vaga
    candidato: Candidato


class AnaliseRequisicao(BaseModel):
    vaga: Vaga
    respostas: list[RespostaItem]


class RelatorioRequisicao(BaseModel):
    vaga: Vaga
    candidato: Candidato
    respostas: list[RespostaItem]
    analise: Analise


def _validar_competencias(vaga: Vaga, respostas: list[RespostaItem]):
    conhecidas = {c.nome for c in vaga.competencias}
    citadas = [r.competencia for r in respostas if r.tipo == "competencia"]

    desconhecidas = {c for c in citadas if c not in conhecidas}
    if desconhecidas:
        raise HTTPException(
            422,
            "Respostas citam competências que não existem na vaga: "
            + ", ".join(sorted(str(c) for c in desconhecidas)),
        )

    duplicadas = [nome for nome, vezes in Counter(citadas).items() if vezes > 1]
    if duplicadas:
        raise HTTPException(
            422,
            "Mais de uma resposta para a mesma competência (o peso contaria em "
            "dobro): " + ", ".join(sorted(duplicadas)),
        )


@router.post("/roteiro")
def rota_roteiro(req: RoteiroRequisicao):
    """Gera o roteiro de perguntas personalizado para o par vaga + candidato."""
    perguntas = gerar_roteiro(req.vaga.model_dump(), req.candidato.model_dump())
    return {"perguntas": perguntas}


@router.post("/transcricao")
def rota_transcricao(
    audio: UploadFile = File(...),
    modelo: str = Form("auto"),
):
    """Transcreve um arquivo de áudio (wav, mp3, ogg, opus, m4a, webm) em PT-BR."""
    if modelo == "auto":
        modelo = escolher_modelo()
    if modelo not in TAMANHOS_ASR:
        raise HTTPException(422, f"Modelo inválido: use um de {TAMANHOS_ASR} ou 'auto'.")

    sufixo = os.path.splitext(audio.filename or "")[1].lower() or ".webm"
    caminho = None
    try:
        with tempfile.NamedTemporaryFile(suffix=sufixo, delete=False) as arquivo:
            caminho = arquivo.name
            shutil.copyfileobj(audio.file, arquivo)
        texto = transcrever(caminho, modelo)
    except AsrOcupadoErro as erro:
        raise HTTPException(503, str(erro))
    except Exception as erro:
        raise HTTPException(500, f"Falha na transcrição: {erro}")
    finally:
        if caminho and os.path.exists(caminho):
            os.unlink(caminho)
    return {"texto": texto, "modelo": modelo}


@router.post("/analise")
def rota_analise(req: AnaliseRequisicao):
    """Analisa a aderência das respostas às competências da vaga.

    Usa LLM (OpenRouter) quando OPENROUTER_API_KEY/OPENROUTER_MODEL estão
    configuradas; caso contrário — ou em falha — usa a análise heurística.
    O campo "metodo" da resposta informa qual caminho foi usado.
    """
    _validar_competencias(req.vaga, req.respostas)
    return analisar_com_fallback(
        req.vaga.model_dump(), [r.model_dump() for r in req.respostas]
    )


@router.post("/relatorio")
def rota_relatorio(req: RelatorioRequisicao):
    """Monta o relatório final (Markdown + JSON) sem gravar nada em disco."""
    texto_md, dados = montar_relatorio(
        req.vaga.model_dump(),
        req.candidato.model_dump(),
        [r.model_dump() for r in req.respostas],
        req.analise.model_dump(),
    )
    return {"relatorio_md": texto_md, "relatorio_json": dados}
