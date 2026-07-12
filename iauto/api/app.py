"""Fábrica da aplicação FastAPI do iAuto.

Uso local ou em deploy:
  python -m iauto.api --porta 8123
  uvicorn iauto.api.app:app
"""

from fastapi import FastAPI

import iauto
from iauto.api import rotas_pipeline, rotas_sessao


def criar_app() -> FastAPI:
    app = FastAPI(
        title="iAuto — Entrevista Automatizada",
        version=iauto.__version__,
    )
    app.include_router(rotas_pipeline.router)
    app.include_router(rotas_sessao.router)
    return app


app = criar_app()
