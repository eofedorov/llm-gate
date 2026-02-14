"""FastAPI entrypoint."""
import logging

from fastapi import FastAPI

from app.api.routes import router
from app.api import routes_rag

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("app").setLevel(logging.INFO)

app = FastAPI(title="LLM-Gate", description="AI-шлюз для инженерных задач")
app.include_router(router, prefix="", tags=["run"])
app.include_router(routes_rag.router, prefix="/rag", tags=["rag"])
