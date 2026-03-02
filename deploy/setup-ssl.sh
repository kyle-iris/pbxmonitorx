#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# PBXMonitorX — Obtain/renew Let's Encrypt SSL certificate
#
# Run after setup.sh if you used --skip-ssl, or if certbot failed.
# Usage: sudo bash deploy/setup-ssl.sh
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

APP_DIR="/opt/pbxmonitorx"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (sudo bash deploy/setup-ssl.sh)"
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
    err "No .env found at $APP_DIR/.env — run setup.sh first"
fi

# Read domain and email from .env
DOMAIN=$(grep '^DOMAIN=' "$APP_DIR/.env" | cut -d= -f2)
EMAIL=$(grep '^EMAIL=' "$APP_DIR/.env" | cut -d= -f2)

if [[ -z "$DOMAIN" ]]; then
    read -rp "Domain name (e.g. monitor.example.com): " DOMAIN
fi
if [[ -z "$EMAIL" ]]; then
    read -rp "Email for Let's Encrypt notifications: " EMAIL
fi

echo ""
echo "Obtaining Let's Encrypt certificate for: $DOMAIN"
echo ""

# Verify DNS resolves to this server
RESOLVED_IP=$(dig +short "$DOMAIN" 2>/dev/null | head -1)
MY_IP=$(curl -sf https://api.ipify.org 2>/dev/null || echo "unknown")

if [[ -n "$RESOLVED_IP" && "$RESOLVED_IP" != "$MY_IP" ]]; then
    warn "DNS for $DOMAIN resolves to $RESOLVED_IP but this server is $MY_IP"
    warn "Certbot will fail if DNS doesn't point here. Continue anyway? (y/N)"
    read -rp "" CONTINUE
    if [[ "$CONTINUE" != "y" && "$CONTINUE" != "Y" ]]; then
        err "Aborted. Fix DNS first, then re-run this script."
    fi
elif [[ -z "$RESOLVED_IP" ]]; then
    warn "Could not resolve $DOMAIN — DNS may not be configured yet."
    warn "Continue anyway? (y/N)"
    read -rp "" CONTINUE
    if [[ "$CONTINUE" != "y" && "$CONTINUE" != "Y" ]]; then
        err "Aborted. Configure DNS first, then re-run this script."
    fi
else
    log "DNS check passed: $DOMAIN → $RESOLVED_IP (matches this server)"
fi

cd "$APP_DIR"

# Swap to HTTP-only nginx config for the ACME challenge
log "Starting temporary HTTP server for ACME challenge..."
CONF="$APP_DIR/deploy/nginx/conf.d/pbxmonitorx.conf"
cp "$CONF" "$CONF.bak"

cat > "$CONF" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'PBXMonitorX SSL setup in progress'; add_header Content-Type text/plain; }
}
EOF

docker compose -f docker-compose.prod.yml up -d nginx
sleep 3

# Run certbot
log "Running certbot..."
if timeout 90 docker compose -f docker-compose.prod.yml run --rm certbot \
    certbot certonly --webroot -w /var/www/certbot \
    --email "$EMAIL" --agree-tos --no-eff-email \
    --non-interactive --force-renewal \
    -d "$DOMAIN"; then
    log "SSL certificate obtained successfully!"
else
    err "Certbot failed. Check that:
  1. DNS for $DOMAIN points to this server ($MY_IP)
  2. Port 80 is open (check Azure NSG / UFW)
  3. No other service is using port 80"
fi

# Restore full config and restart
log "Restoring full nginx configuration..."
cp "$CONF.bak" "$CONF"
rm -f "$CONF.bak"

docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

log "Done! Site is live at https://$DOMAIN"
