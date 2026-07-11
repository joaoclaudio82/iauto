"""Geração de roteiro personalizado de perguntas (módulo iAuto).

Correlaciona o perfil do candidato com os requisitos da vaga e monta a
sequência de perguntas da entrevista.
"""

import unicodedata


def normalizar(texto):
    """Converte para minúsculas e remove acentos, para comparação de termos."""
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _experiencia_relacionada(candidato, palavras_chave):
    """Busca no currículo uma experiência ligada à competência avaliada."""
    for exp in candidato.get("experiencias", []):
        exp_norm = normalizar(exp)
        for termo in palavras_chave:
            if normalizar(termo) in exp_norm:
                return exp
    return None


def gerar_roteiro(vaga, candidato):
    """Monta o roteiro completo da entrevista.

    Cada item tem: id, tipo, competencia, pergunta e tempo_max (segundos).
    """
    primeiro_nome = candidato["nome"].split()[0]

    roteiro = [{
        "id": 1,
        "tipo": "abertura",
        "competencia": None,
        "pergunta": (
            f"Olá, {primeiro_nome}. Esta é uma entrevista automatizada para a vaga "
            f"de {vaga['titulo']}. Para começar, fale brevemente sobre a sua "
            "trajetória profissional e o que mais chamou a sua atenção nesta vaga."
        ),
        "tempo_max": 90,
    }]

    proximo_id = 2
    for comp in vaga["competencias"]:
        experiencia = _experiencia_relacionada(candidato, comp["palavras_chave"])
        if experiencia:
            pergunta = (
                f"No seu currículo consta a seguinte experiência: {experiencia}. "
                f"Conte com mais detalhes como foi essa atuação, com foco em "
                f"{comp['nome']}: qual era o problema, o que você fez e qual foi "
                "o resultado."
            )
        else:
            pergunta = (
                f"Descreva uma situação real em que você precisou aplicar "
                f"{comp['nome']}. Explique o contexto, as suas ações e o "
                "resultado obtido."
            )
        roteiro.append({
            "id": proximo_id,
            "tipo": "competencia",
            "competencia": comp["nome"],
            "pergunta": pergunta,
            "tempo_max": 120,
        })
        proximo_id += 1

    roteiro.append({
        "id": proximo_id,
        "tipo": "situacional",
        "competencia": None,
        "pergunta": (
            "Imagine que uma entrega importante sob a sua responsabilidade está "
            "atrasada e outra área depende desse resultado ainda nesta semana. "
            "Descreva como você conduziria essa situação."
        ),
        "tempo_max": 90,
    })

    roteiro.append({
        "id": proximo_id + 1,
        "tipo": "encerramento",
        "competencia": None,
        "pergunta": (
            "Para finalizar, existe algum ponto relevante sobre você que não foi "
            "perguntado e que gostaria de registrar?"
        ),
        "tempo_max": 60,
    })

    return roteiro
