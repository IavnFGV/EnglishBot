#!/bin/sh
set -eu

TEMPLATE_PATH="/etc/nginx/templates/englishbot-webapp.conf.template"
OUTPUT_PATH="/etc/nginx/conf.d/default.conf"
FULLCHAIN_PATH="/etc/nginx/certs/fullchain.pem"
PRIVKEY_PATH="/etc/nginx/certs/privkey.pem"

if [ -f "${FULLCHAIN_PATH}" ] && [ -f "${PRIVKEY_PATH}" ]; then
  HTTPS_REDIRECT_BLOCK='
    location / {
        return 301 https://$host$request_uri;
    }
'
  HTTPS_SERVER_BLOCK="
server {
    listen 443 ssl;
    http2 on;
    server_name _;

    ssl_certificate ${FULLCHAIN_PATH};
    ssl_certificate_key ${PRIVKEY_PATH};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;

    location / {
        proxy_pass http://englishbot-webapp:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 60s;
    }
}
"
else
  HTTPS_REDIRECT_BLOCK='
    location / {
        proxy_pass http://englishbot-webapp:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }
'
  HTTPS_SERVER_BLOCK=""
fi

mkdir -p "$(dirname "${OUTPUT_PATH}")"

awk \
  -v https_redirect_block="${HTTPS_REDIRECT_BLOCK}" \
  -v https_server_block="${HTTPS_SERVER_BLOCK}" \
  '
    {
      gsub(/\{\{HTTPS_REDIRECT_BLOCK\}\}/, https_redirect_block)
      gsub(/\{\{HTTPS_SERVER_BLOCK\}\}/, https_server_block)
      print
    }
  ' "${TEMPLATE_PATH}" > "${OUTPUT_PATH}"
