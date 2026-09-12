#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CERT_DIR="$ROOT/infra/certs"
SECRET_FILE="$ROOT/infra/secrets/session_signing_secret"
mkdir -p "$CERT_DIR" "$(dirname "$SECRET_FILE")"
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 365 \
  -keyout "$CERT_DIR/nexus-localhost.key" -out "$CERT_DIR/nexus-localhost.crt" \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,DNS:*.localhost"
openssl rand -hex 32 > "$SECRET_FILE"
chmod 600 "$CERT_DIR/nexus-localhost.key" "$SECRET_FILE"
printf 'Local TLS certificate and session secret created.\n'
