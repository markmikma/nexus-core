from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Nexus-Core GitOps Deploy Sikeres!",
    }
