from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Nexus-Core GitOps deploy: commit-alapú v2!",
    	"gitops_revision": "true-gitea-commit-v3",
	}
