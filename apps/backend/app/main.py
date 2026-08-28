from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.generation import router as generation_router
from app.api.research import router as research_router
from app.api.topics import router as topics_router


app = FastAPI(
    title="PostMesh API",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=False,
    allow_methods=[
        "GET",
        "POST",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Content-Type",
    ],
)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "postmesh-api",
    }


app.include_router(topics_router)
app.include_router(research_router)
app.include_router(generation_router)