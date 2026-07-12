"""Rotas atômicas do pipeline iAuto, para consumo por outros backends.

Diferente do fluxo de sessão da entrevista web (rotas_sessao), estas rotas são
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
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from iauto.api.esquemas import AnaliseRequisicao, RelatorioRequisicao, RoteiroRequisicao
from iauto.dominio.modelos import Resposta, Vaga
from iauto.dominio.relatorio import montar_relatorio
from iauto.dominio.roteiro import gerar_roteiro
from iauto.servicos.analise_llm import analisar_com_fallback
from iauto.servicos.transcricao import AsrOcupadoErro, escolher_modelo, transcrever

router = APIRouter(prefix="/api/v1", tags=["pipeline"])

TAMANHOS_ASR = ("tiny", "base", "small", "medium")


def _validar_competencias(vaga: Vaga, respostas: Sequence[Resposta]) -> None:
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
    return {"perguntas": gerar_roteiro(req.vaga, req.candidato)}


@router.post("/transcricao")
def rota_transcricao(
    audio: Annotated[UploadFile, File()],
    modelo: Annotated[str, Form()] = "auto",
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
        raise HTTPException(503, str(erro)) from erro
    except Exception as erro:
        raise HTTPException(500, f"Falha na transcrição: {erro}") from erro
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
    return analisar_com_fallback(req.vaga, req.respostas)


@router.post("/relatorio")
def rota_relatorio(req: RelatorioRequisicao):
    """Monta o relatório final (Markdown + JSON) sem gravar nada em disco."""
    texto_md, dados = montar_relatorio(req.vaga, req.candidato, req.respostas, req.analise)
    return {"relatorio_md": texto_md, "relatorio_json": dados}
