"""Análise heurística de aderência das respostas às competências da vaga.

A pontuação é determinística: cobertura de termos da competência (60 pontos),
profundidade da resposta (25 pontos) e presença de exemplo concreto ou
resultado (15 pontos). A camada semântica com LLM (iauto.servicos.analise_llm)
complementa esta análise e cai para ela em caso de falha.
"""

import re
from collections.abc import Sequence

from iauto.dominio.modelos import Analise, AvaliacaoCompetencia, Resposta, Vaga
from iauto.dominio.roteiro import normalizar

PALAVRAS_MINIMAS = 15

# Limiares compartilhados entre a análise heurística e a análise por LLM.
NOTA_ADERENTE = 70
NOTA_PARCIAL = 40

MARCADORES_EXEMPLO = [
    "por exemplo",
    "na epoca",
    "no projeto",
    "quando eu",
    "eu fiz",
    "a gente fez",
    "implementei",
    "criei",
    "construi",
    "montei",
    "resolvi",
    "resultado",
    "conseguimos",
    "consegui",
    "reduzi",
    "aumentei",
    "entreguei",
]


def cobertura(resposta_norm: str, palavras_chave: Sequence[str]) -> tuple[float, list[str]]:
    """Proporção e lista de palavras-chave da competência presentes na resposta."""
    termos_norm = [normalizar(termo) for termo in palavras_chave]
    encontrados = [
        original
        for original, termo in zip(palavras_chave, termos_norm, strict=False)
        if termo in resposta_norm
    ]
    proporcao = len(encontrados) / len(palavras_chave) if palavras_chave else 0.0
    return proporcao, encontrados


def situacao_por_nota(nota: int, resposta: str) -> str:
    """Regra compartilhada de classificação da situação de uma competência."""
    if not resposta.strip():
        return "lacuna"
    if nota >= NOTA_ADERENTE:
        return "aderente"
    if nota >= NOTA_PARCIAL:
        return "parcial"
    return "lacuna"


def recomendacao_por_nota(nota_geral: int, lacunas: Sequence[str]) -> str:
    """Regra compartilhada da frase de recomendação final."""
    if nota_geral >= NOTA_ADERENTE and not lacunas:
        return "Recomendado para a próxima etapa do processo."
    if nota_geral >= 50:
        return "Aderência intermediária. Avaliar com atenção os riscos e as lacunas indicados."
    return "Aderência baixa aos requisitos desta vaga."


def _trechos_relevantes(resposta: str, palavras_chave: Sequence[str], limite: int = 2) -> list[str]:
    """Extrai as frases da resposta que citam termos da competência."""
    termos_norm = [normalizar(termo) for termo in palavras_chave]
    frases = re.split(r"(?<=[.!?])\s+", resposta)
    achados = []
    for frase in frases:
        frase_norm = normalizar(frase)
        if any(termo in frase_norm for termo in termos_norm):
            achados.append(frase.strip())
        if len(achados) >= limite:
            break
    return achados


def avaliar_resposta(resposta: str, palavras_chave: Sequence[str]) -> dict:
    """Avalia uma resposta transcrita em relação a uma competência."""
    resposta = (resposta or "").strip()
    resposta_norm = normalizar(resposta)
    n_palavras = len(resposta.split())

    proporcao, termos = cobertura(resposta_norm, palavras_chave)
    tem_exemplo = any(marcador in resposta_norm for marcador in MARCADORES_EXEMPLO)

    pontos_termos = 60.0 * min(1.0, proporcao / 0.5)
    pontos_profundidade = 25.0 * min(1.0, n_palavras / 80.0)
    pontos_exemplo = 15.0 if tem_exemplo else 0.0
    nota = round(pontos_termos + pontos_profundidade + pontos_exemplo)

    riscos = []
    if not resposta:
        riscos.append("pergunta ficou sem resposta")
    elif n_palavras < PALAVRAS_MINIMAS:
        riscos.append("resposta muito curta, com pouco conteúdo avaliável")
    if resposta and not tem_exemplo:
        riscos.append("não apresentou exemplo concreto nem resultado")

    return {
        "nota": nota,
        "situacao": situacao_por_nota(nota, resposta),
        "termos_identificados": termos,
        "trechos_relevantes": _trechos_relevantes(resposta, palavras_chave),
        "tem_exemplo": tem_exemplo,
        "n_palavras": n_palavras,
        "riscos": riscos,
    }


def analisar_entrevista(vaga: Vaga, respostas: Sequence[Resposta]) -> Analise:
    """Consolida a aderência por competência e a recomendação final."""
    mapa_competencias = {c.nome: c for c in vaga.competencias}

    avaliacoes = []
    for item in respostas:
        if item.tipo != "competencia":
            continue
        competencia = mapa_competencias[item.competencia]
        crua = avaliar_resposta(item.resposta, competencia.palavras_chave)
        avaliacoes.append(
            AvaliacaoCompetencia(
                competencia=competencia.nome,
                peso=competencia.peso,
                **crua,
            )
        )

    soma_pesos = sum(a.peso for a in avaliacoes) or 1
    nota_geral = round(sum(a.nota * a.peso for a in avaliacoes) / soma_pesos)

    destaques = [a.competencia for a in avaliacoes if a.situacao == "aderente"]
    lacunas = [a.competencia for a in avaliacoes if a.situacao == "lacuna"]
    riscos = [f"{a.competencia}: {risco}" for a in avaliacoes for risco in a.riscos]

    return Analise(
        nota_geral=nota_geral,
        recomendacao=recomendacao_por_nota(nota_geral, lacunas),
        avaliacoes=avaliacoes,
        destaques=destaques,
        riscos=riscos,
        lacunas=lacunas,
        metodo="heuristico",
    )
