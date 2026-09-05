import subprocess
from pathlib import Path


def audit_python_dependencies(app_dir: Path) -> None:
    requirements_file = app_dir / "requirements.txt"

    if not requirements_file.is_file():
        raise RuntimeError(
            f"Security gate: hiányzik a függőségek fájlja: {requirements_file}"
        )

    result = subprocess.run(
        ["pip-audit", "-r", str(requirements_file), "--format", "json"],
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        details = (result.stdout + "\n" + result.stderr).strip()
        raise RuntimeError(
            "Security gate: dependency audit sikertelen; deploy blokkolva.\n"
            + details[-4000:]
        )