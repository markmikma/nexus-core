from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram, make_asgi_app
import time

app = FastAPI()

HTTP_REQUESTS = Counter(
    "nexus_http_requests_total",
    "HTTP requests handled by Nexus-Core services.",
    ("service", "method", "path", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "nexus_http_request_duration_seconds",
    "HTTP request duration handled by Nexus-Core services.",
    ("service", "method", "path"),
)


@app.middleware("http")
async def collect_http_metrics(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    labels = ("sample-app", request.method, request.url.path)
    HTTP_REQUESTS.labels(*labels, str(response.status_code)).inc()
    HTTP_REQUEST_DURATION.labels(*labels).observe(time.perf_counter() - started)
    return response


app.mount("/metrics", make_asgi_app())


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
