#!/usr/bin/env bash
set -euo pipefail

DEPLOY_USER="deploy"
DEPLOY_HOME="/home/${DEPLOY_USER}"
APP_ROOT="/srv/englishbot"
ROOT_AUTH_KEYS="/root/.ssh/authorized_keys"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root"
  exit 1
fi

if [[ ! -f "${ROOT_AUTH_KEYS}" ]]; then
  echo "Root authorized_keys not found: ${ROOT_AUTH_KEYS}"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Updating system"
apt update
apt upgrade -y

echo "==> Installing Docker and security tools"
apt install -y docker.io docker-compose-v2 ufw fail2ban

echo "==> Enabling Docker"
systemctl enable docker
systemctl start docker

if ! id "${DEPLOY_USER}" >/dev/null 2>&1; then
  echo "==> Creating deploy user"
  adduser --disabled-password --gecos "" "${DEPLOY_USER}"
fi

echo "==> Granting access"
usermod -aG sudo "${DEPLOY_USER}"
usermod -aG docker "${DEPLOY_USER}"

echo "==> Copying root SSH keys to deploy user"
mkdir -p "${DEPLOY_HOME}/.ssh"
cp "${ROOT_AUTH_KEYS}" "${DEPLOY_HOME}/.ssh/authorized_keys"
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${DEPLOY_HOME}/.ssh"
chmod 700 "${DEPLOY_HOME}/.ssh"
chmod 600 "${DEPLOY_HOME}/.ssh/authorized_keys"

echo "==> Preparing app directories"
mkdir -p "${APP_ROOT}/app"
mkdir -p "${APP_ROOT}/shared/data"
mkdir -p "${APP_ROOT}/shared/assets"
mkdir -p "${APP_ROOT}/shared/backups/db"
mkdir -p "${APP_ROOT}/shared/backups/db-versioned"
mkdir -p "${APP_ROOT}/shared/content/custom"
mkdir -p "${APP_ROOT}/shared/deploy"
mkdir -p "${APP_ROOT}/shared/logs"
touch "${APP_ROOT}/shared/.env"
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_ROOT}"

echo "==> Configuring firewall"
ufw allow OpenSSH
ufw --force enable

echo "==> Enabling fail2ban"
systemctl enable fail2ban
systemctl restart fail2ban

echo "==> Hardening SSH"
SSHD_CONFIG="/etc/ssh/sshd_config"

sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "${SSHD_CONFIG}" || true
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "${SSHD_CONFIG}" || true
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' "${SSHD_CONFIG}" || true

grep -q '^PermitRootLogin' "${SSHD_CONFIG}" || echo 'PermitRootLogin no' >> "${SSHD_CONFIG}"
grep -q '^PasswordAuthentication' "${SSHD_CONFIG}" || echo 'PasswordAuthentication no' >> "${SSHD_CONFIG}"
grep -q '^PubkeyAuthentication' "${SSHD_CONFIG}" || echo 'PubkeyAuthentication yes' >> "${SSHD_CONFIG}"

sshd -t
systemctl restart ssh || systemctl restart sshd

echo
echo "Done."
echo "Test SSH login as ${DEPLOY_USER} before closing the root session."
echo "App root: ${APP_ROOT}"
echo "Shared env: ${APP_ROOT}/shared/.env"
