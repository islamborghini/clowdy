#!/usr/bin/env bash
#
# Put Clowdy on a fresh Ubuntu VM, as a public read-only demo.
#
#   curl -fsSL https://raw.githubusercontent.com/islamborghini/clowdy/version_control/scripts/deploy.sh | sudo bash
#
# Works on any Ubuntu 22.04 or 24.04 box with a public IP -- Oracle Always
# Free, GCP e2-micro, AWS t3.micro, a VPS. Architecture is detected, so arm64
# and amd64 both work.
#
# Deliberately not Terraform. The Terraform in infra/ describes the real
# multi-node architecture and is worth reading; for getting one box running,
# clicking "create instance" in a console and pasting one command is fewer
# moving parts than an API key, a fingerprint, a pem file and a state file.
#
# Idempotent: safe to re-run to pick up new commits.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/islamborghini/clowdy.git}"
REPO_BRANCH="${REPO_BRANCH:-version_control}"
APP_DIR="${APP_DIR:-/opt/clowdy}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.demo.yml"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Run this as root (prefix the command with sudo)."

log "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # Detect the architecture rather than hardcoding it, so this same script
  # works on Graviton/Ampere (arm64) and on Intel free tiers (amd64).
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null
fi
systemctl enable --now docker
command -v docker >/dev/null || fail "Docker did not install."

log "Opening HTTP on the host firewall"
# Cloud images (Oracle's especially) ship an iptables policy that drops
# everything except SSH. Opening the port in the provider's security list is
# necessary but not sufficient -- the host has to allow it too. This is the
# single most common reason a deploy looks fine and the browser times out.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null || true
else
  if ! iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
  fi
  # Persist it, or the rule is gone after the first reboot.
  if ! command -v netfilter-persistent >/dev/null 2>&1; then
    apt-get install -y -qq iptables-persistent >/dev/null 2>&1 || true
  fi
  command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save >/dev/null 2>&1 || true
fi

# Free-tier boxes are often 1GB, and `docker build` is the memory-hungriest
# thing this script does -- four images, one of them a Node build. Without
# swap the build gets OOM-killed and the deploy fails with a confusing error.
# Swap is the difference between "works on the free tier" and "works on my
# machine".
TOTAL_MB="$(free -m | awk '/^Mem:/ {print $2}')"
if [ "${TOTAL_MB:-9999}" -lt 2048 ] && [ ! -f /swapfile ]; then
  log "Adding 2GB of swap (only ${TOTAL_MB}MB of RAM)"
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Small boxes cannot hold two control planes and three workers alongside
# Postgres. The overlay drops to one control plane and two workers, which is
# still a real fleet with real placement between them.
if [ "${TOTAL_MB:-9999}" -lt 2048 ]; then
  COMPOSE="$COMPOSE -f docker-compose.small.yml"
  log "Small host detected, using the reduced fleet"
fi

log "Fetching the code"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --depth 1 origin "$REPO_BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$REPO_BRANCH"
else
  git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# No API keys on a public box. Without them the AI assistant and managed
# databases stay inert, which is what a read-only demo wants anyway, and there
# is nothing on the host worth stealing.
touch "$APP_DIR/.env"

log "Building and starting (first run takes 5-10 minutes)"
$COMPOSE up -d --build

log "Waiting for the API"
for _ in $(seq 1 60); do
  if curl -fsS http://localhost/api/health >/dev/null 2>&1; then break; fi
  sleep 5
done
curl -fsS http://localhost/api/health >/dev/null 2>&1 || {
  $COMPOSE ps
  fail "API never came up. Check: cd $APP_DIR && $COMPOSE logs control-plane"
}

log "Seeding the demo functions"
$COMPOSE exec -T control-plane python -m app.seed_demo || true

log "Installing the systemd unit so it survives reboots"
cat > /etc/systemd/system/clowdy.service <<UNIT
[Unit]
Description=Clowdy
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/$COMPOSE up -d
ExecStop=/usr/bin/$COMPOSE down

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable clowdy.service >/dev/null 2>&1 || true

log "Checking it actually works"
bash "$APP_DIR/scripts/verify_deploy.sh" http://localhost || fail "Deployed, but the checks did not pass."

PUBLIC_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo "")"
log "Done"
if [ -n "$PUBLIC_IP" ]; then
  echo "    http://$PUBLIC_IP"
  echo
  echo "  If that does not load from your laptop, the VM is serving fine but"
  echo "  your provider's firewall is still closed. Allow inbound TCP 80 in the"
  echo "  security list / security group / VPC firewall rule."
else
  echo "    Serving on port 80."
fi
