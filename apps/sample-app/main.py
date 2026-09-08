from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
def healthz():
    """Used by the deployment worker before a release is promoted."""
    return {"status": "ok", "service": "sample-app"}


@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Nexus-Core GitOps deploy: commit-alapú v2!",
    	"gitops_revision": "true-gitea-commit-v3",
	}
