from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import router as v1_router
from app.api.v1.persistent_store import bootstrap_demo_data

app = FastAPI(title="FantasyCabinet API", version="0.1.0")
app.include_router(v1_router, prefix="/api/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    bootstrap_demo_data()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
