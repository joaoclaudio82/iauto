"""Ponto de entrada do servidor: ``python -m iauto.api``."""

import argparse
import logging
import os

import uvicorn

from iauto.api.app import app
from iauto.api.contexto import contexto


def principal() -> None:
    parser = argparse.ArgumentParser(description="Servidor web do iAuto")
    parser.add_argument("--vaga", help="arquivo JSON da vaga")
    parser.add_argument("--candidato", help="arquivo JSON do candidato")
    parser.add_argument(
        "--modelo",
        default=os.environ.get("MODELO_ASR", "auto"),
        help="tiny, base, small, medium ou auto (small se já baixado)",
    )
    parser.add_argument(
        "--porta",
        type=int,
        default=int(os.environ.get("PORT", "8123")),
        help="porta HTTP (padrão: variável PORT ou 8123)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="endereço de escuta (use 0.0.0.0 em deploy)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    contexto.configurar(args.vaga, args.candidato, args.modelo)
    print(f"[iAuto] Modelo ASR: {contexto.modelo}")
    print(f"[iAuto] Escutando em http://{args.host}:{args.porta}")
    uvicorn.run(app, host=args.host, port=args.porta)


if __name__ == "__main__":
    principal()
