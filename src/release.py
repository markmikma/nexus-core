"""Release environment policy for controlled GitOps promotion."""

ENVIRONMENTS = ("dev", "staging", "production")


def deployment_app_name(environment: str) -> str:
    if environment not in ENVIRONMENTS:
        raise ValueError("Unknown deployment environment.")
    return "sample-app" if environment == "production" else f"sample-app-{environment}"


def can_promote(source: str, target: str) -> bool:
    try:
        return ENVIRONMENTS.index(target) == ENVIRONMENTS.index(source) + 1
    except ValueError:
        return False
