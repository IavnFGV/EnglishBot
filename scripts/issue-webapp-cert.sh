#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/englishbot/app}"
SHARED_DIR="${SHARED_DIR:-/srv/englishbot/shared}"
ENV_FILE="${ENV_FILE:-${SHARED_DIR}/.env}"
ACME_DIR="${ACME_DIR:-${SHARED_DIR}/nginx/acme}"
CERT_LINK_DIR="${CERT_LINK_DIR:-${SHARED_DIR}/nginx/certs}"
NGINX_SERVICE_NAME="${NGINX_SERVICE_NAME:-englishbot-nginx}"
WEB_APP_BASE_URL="${WEB_APP_BASE_URL:-}"
DOMAIN="${1:-}"
EMAIL="${CERTBOT_EMAIL:-}"

if [[ -z "${DOMAIN}" ]] && [[ -f "${ENV_FILE}" ]]; then
  WEB_APP_BASE_URL="$(grep '^WEB_APP_BASE_URL=' "${ENV_FILE}" | cut -d= -f2- || true)"
  if [[ -n "${WEB_APP_BASE_URL}" ]]; then
    DOMAIN="$(printf '%s' "${WEB_APP_BASE_URL}" | sed -E 's#^https?://([^/]+).*$#\1#')"
  fi
fi

if [[ -z "${DOMAIN}" ]]; then
  echo "Usage: CERTBOT_EMAIL=you@example.com bash scripts/issue-webapp-cert.sh <domain>" >&2
  echo "Or set WEB_APP_BASE_URL in ${ENV_FILE} and omit the domain argument." >&2
  exit 1
fi

if [[ -z "${EMAIL}" ]]; then
  echo "CERTBOT_EMAIL is required." >&2
  exit 1
fi

if [[ ! -d "${APP_DIR}" ]]; then
  echo "App directory does not exist: ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}" >&2
  exit 1
fi

if ! command -v certbot >/dev/null 2>&1; then
  echo "certbot is not installed. Run: sudo apt-get update && sudo apt-get install -y certbot" >&2
  exit 1
fi

mkdir -p "${ACME_DIR}"
mkdir -p "${CERT_LINK_DIR}"

cd "${APP_DIR}"

echo "==> Starting or refreshing runtime containers"
docker compose up -d --build --force-recreate

echo "==> Requesting Let's Encrypt certificate for ${DOMAIN}"
sudo certbot certonly \
  --webroot \
  -w "${ACME_DIR}" \
  --email "${EMAIL}" \
  --agree-tos \
  --non-interactive \
  -d "${DOMAIN}"

LIVE_DIR="/etc/letsencrypt/live/${DOMAIN}"
FULLCHAIN_SOURCE="${LIVE_DIR}/fullchain.pem"
PRIVKEY_SOURCE="${LIVE_DIR}/privkey.pem"

if [[ ! -f "${FULLCHAIN_SOURCE}" ]] || [[ ! -f "${PRIVKEY_SOURCE}" ]]; then
  echo "Expected certificate files were not created in ${LIVE_DIR}" >&2
  exit 1
fi

ln -sfn "${FULLCHAIN_SOURCE}" "${CERT_LINK_DIR}/fullchain.pem"
ln -sfn "${PRIVKEY_SOURCE}" "${CERT_LINK_DIR}/privkey.pem"

echo "==> Restarting ${NGINX_SERVICE_NAME}"
docker compose restart "${NGINX_SERVICE_NAME}"

echo "==> Certificate is active for https://${DOMAIN}"
