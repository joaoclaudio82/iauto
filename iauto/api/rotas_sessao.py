"""Rotas da entrevista web: página, sessão, respostas, relatório e voz.

Este é o fluxo com estado que atende ``web/index.html``: uma sessão por
entrevista, com o par vaga/candidato ativo do processo (ver contexto.py).
"""

import os
import threading
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from iauto.api.contexto import CAMINHO_INDEX, PASTA_SAIDA, Sessao, contexto
from iauto.dominio.modelos import Resposta
from iauto.dominio.relatorio import gerar_relatorio
from iauto.dominio.roteiro import gerar_roteiro
from iauto.servicos import tts
from iauto.servicos.analise_llm import analisar_com_fallback
from iauto.servicos.transcricao import AsrOcupadoErro, carregar_modelo, transcrever

router = APIRouter(tags=["entrevista-web"])

EXTENSAO_POR_TIPO = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


def _criar_pasta_saida(nome_candidato: str) -> str:
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    nome = nome_candidato.split()[0].lower()
    pasta = PASTA_SAIDA / f"{carimbo}_{nome}_web"
    pasta.mkdir(parents=True, exist_ok=True)
    return str(pasta)


def _carregar_asr() -> None:
    """Pré-carrega o modelo ASR para a primeira transcrição não esperar."""
    try:
        carregar_modelo(contexto.modelo)
    except Exception:  # pragma: no cover - melhor esforço, logado no serviço
        pass


@router.get("/")
def pagina():
    if not CAMINHO_INDEX.exists():
        raise HTTPException(500, "Interface web não encontrada (web/index.html).")
    return FileResponse(CAMINHO_INDEX, media_type="text/html")


@router.get("/api/info")
def informacoes():
    contexto.garantir_configuracao()
    return {
        "vaga": contexto.vaga,
        "candidato": contexto.candidato,
        "modelo_asr": contexto.modelo,
    }


@router.get("/api/tts")
async def sintetizar_voz(texto: str):
    try:
        audio = await tts.sintetizar(texto)
    except tts.TextoInvalidoErro as erro:
        raise HTTPException(400, str(erro)) from erro
    except Exception as erro:
        raise HTTPException(503, f"Voz neural indisponível: {erro}") from erro
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/api/sessao")
def criar_sessao():
    contexto.garantir_configuracao()
    vaga, candidato = contexto.vaga, contexto.candidato
    roteiro = gerar_roteiro(vaga, candidato)
    sessao_id = uuid.uuid4().hex[:12]
    contexto.sessoes[sessao_id] = Sessao(
        vaga=vaga,
        candidato=candidato,
        roteiro=roteiro,
        pasta=_criar_pasta_saida(candidato.nome),
    )
    threading.Thread(target=_carregar_asr, daemon=True).start()
    return {
        "sessao_id": sessao_id,
        "candidato": candidato.nome,
        "vaga": vaga.titulo,
        "empresa": vaga.empresa,
        "modelo_asr": contexto.modelo,
        "perguntas": roteiro,
    }


@router.post("/api/sessao/{sessao_id}/resposta/{pergunta_id}")
def receber_resposta(
    sessao_id: str,
    pergunta_id: int,
    audio: Annotated[UploadFile | None, File()] = None,
    texto: Annotated[str | None, Form()] = None,
):
    sessao = contexto.sessoes.get(sessao_id)
    if not sessao:
        raise HTTPException(404, "Sessão não encontrada.")
    pergunta = next((p for p in sessao.roteiro if p.id == pergunta_id), None)
    if not pergunta:
        raise HTTPException(404, "Pergunta não encontrada.")

    item = Resposta(**pergunta.model_dump())
    if audio is not None and (audio.filename or audio.content_type):
        extensao = os.path.splitext(audio.filename or "")[1].lower()
        if not extensao:
            extensao = EXTENSAO_POR_TIPO.get(audio.content_type, ".webm")
        caminho = os.path.join(sessao.pasta, f"resposta_{pergunta_id:02d}{extensao}")
        with open(caminho, "wb") as destino:
            destino.write(audio.file.read())
        item.arquivo_audio = caminho

        try:
            item.resposta = transcrever(caminho, contexto.modelo)
        except AsrOcupadoErro as erro:
            raise HTTPException(503, str(erro)) from erro
        except Exception as erro:
            raise HTTPException(500, f"Falha na transcrição: {erro}") from erro
    else:
        item.resposta = (texto or "").strip()

    sessao.respostas[pergunta_id] = item
    return {"pergunta_id": pergunta_id, "transcricao": item.resposta}


@router.post("/api/sessao/{sessao_id}/finalizar")
def finalizar(sessao_id: str):
    sessao = contexto.sessoes.get(sessao_id)
    if not sessao:
        raise HTTPException(404, "Sessão não encontrada.")

    respostas = [sessao.respostas.get(p.id) or Resposta(**p.model_dump()) for p in sessao.roteiro]

    analise = analisar_com_fallback(sessao.vaga, respostas)
    caminho_md, caminho_json = gerar_relatorio(
        sessao.vaga, sessao.candidato, respostas, analise, sessao.pasta
    )
    with open(caminho_md, encoding="utf-8") as arquivo:
        conteudo_md = arquivo.read()

    resultado = {
        "sessao_id": sessao_id,
        "candidato": sessao.candidato.nome,
        "vaga": sessao.vaga.titulo,
        "empresa": sessao.vaga.empresa,
        "analise": analise,
        "respostas": respostas,
        "caminho_md": caminho_md,
        "caminho_json": caminho_json,
        "relatorio_md": conteudo_md,
    }
    sessao.finalizada = resultado
    return resultado


@router.get("/api/sessao/{sessao_id}/arquivo/{tipo}")
def baixar_arquivo(sessao_id: str, tipo: str):
    sessao = contexto.sessoes.get(sessao_id)
    if not sessao or not sessao.finalizada:
        raise HTTPException(404, "Relatório ainda não gerado para esta sessão.")
    if tipo == "md":
        return FileResponse(sessao.finalizada["caminho_md"], filename="relatorio.md")
    if tipo == "json":
        return FileResponse(sessao.finalizada["caminho_json"], filename="relatorio.json")
    raise HTTPException(404, "Tipo de arquivo inválido (use md ou json).")
