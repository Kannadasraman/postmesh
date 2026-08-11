from fastapi import FastAPI

app = FastAPI(
    title="PostMesh API",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "postmesh-api",
    }