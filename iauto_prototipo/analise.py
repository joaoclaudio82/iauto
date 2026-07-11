"""Normalização das respostas, extração de trechos relevantes e análise de
aderência por competência.

A pontuação é heurística, pensada para o protótipo: cobertura de termos da
competência (60 pontos), profundidade da resposta (25 pontos) e presença de
exemplo concreto ou resultado (15 pontos). O próximo passo natural é trocar
esta camada por análise semântica com embeddings ou com um LLM.
"""

import re

from roteiro import normalizar

PALAVRAS_MINIMAS = 15

MARCADORES_EXEMPLO = [
    "por exemplo", "na epoca", "no projeto", "quando eu", "eu fiz",
    "a gente fez", "implementei", "criei", "construi", "montei", "resolvi",
    "resultado", "conseguimos", "consegui", "reduzi", "aumentei", "entreguei",
]


def _cobertura(resposta_norm, palavras_chave):
    termos_norm = [normalizar(termo) for termo in palavras_chave]
    encontrados = [
        original for original, termo in zip(palavras_chave, termos_norm)
        if termo in resposta_norm
    ]
    proporcao = len(encontrados) / len(palavras_chave) if palavras_chave else 0.0
    return proporcao, encontrados


def _trechos_relevantes(resposta, palavras_chave, limite=2):
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


def avaliar_resposta(resposta, palavras_chave):
    """Avalia uma resposta transcrita em relação a uma competência."""
    resposta = (resposta or "").strip()
    resposta_norm = normalizar(resposta)
    n_palavras = len(resposta.split())

    proporcao, termos = _cobertura(resposta_norm, palavras_chave)
    tem_exemplo = any(marcador in resposta_norm for marcador in MARCADORES_EXEMPLO)

    pontos_termos = 60.0 * min(1.0, proporcao / 0.5)
    pontos_profundidade = 25.0 * min(1.0, n_palavras / 80.0)
    pontos_exemplo = 15.0 if tem_exemplo else 0.0
    nota = round(pontos_termos + pontos_profundidade + pontos_exemplo)

    if not resposta:
        situacao = "lacuna"
    elif nota >= 70:
        situacao = "aderente"
    elif nota >= 40:
        situacao = "parcial"
    else:
        situacao = "lacuna"

    riscos = []
    if not resposta:
        riscos.append("pergunta ficou sem resposta")
    elif n_palavras < PALAVRAS_MINIMAS:
        riscos.append("resposta muito curta, com pouco conteúdo avaliável")
    if resposta and not tem_exemplo:
        riscos.append("não apresentou exemplo concreto nem resultado")

    return {
        "nota": nota,
        "situacao": situacao,
        "termos_identificados": termos,
        "trechos_relevantes": _trechos_relevantes(resposta, palavras_chave),
        "tem_exemplo": tem_exemplo,
        "n_palavras": n_palavras,
        "riscos": riscos,
    }


def analisar_entrevista(vaga, respostas):
    """Consolida a aderência por competência e a recomendação final."""
    mapa_competencias = {c["nome"]: c for c in vaga["competencias"]}

    avaliacoes = []
    for item in respostas:
        if item.get("tipo") != "competencia":
            continue
        competencia = mapa_competencias[item["competencia"]]
        avaliacao = avaliar_resposta(item.get("resposta", ""), competencia["palavras_chave"])
        avaliacao["competencia"] = competencia["nome"]
        avaliacao["peso"] = competencia.get("peso", 1)
        avaliacoes.append(avaliacao)

    soma_pesos = sum(a["peso"] for a in avaliacoes) or 1
    nota_geral = round(sum(a["nota"] * a["peso"] for a in avaliacoes) / soma_pesos)

    destaques = [a["competencia"] for a in avaliacoes if a["situacao"] == "aderente"]
    lacunas = [a["competencia"] for a in avaliacoes if a["situacao"] == "lacuna"]
    riscos = [
        f"{a['competencia']}: {risco}"
        for a in avaliacoes
        for risco in a["riscos"]
    ]

    if nota_geral >= 70 and not lacunas:
        recomendacao = "Recomendado para a próxima etapa do processo."
    elif nota_geral >= 50:
        recomendacao = (
            "Aderência intermediária. Avaliar com atenção os riscos e as "
            "lacunas indicados."
        )
    else:
        recomendacao = "Aderência baixa aos requisitos desta vaga."

    return {
        "nota_geral": nota_geral,
        "recomendacao": recomendacao,
        "avaliacoes": avaliacoes,
        "destaques": destaques,
        "riscos": riscos,
        "lacunas": lacunas,
    }
