#!/bin/sh
set -e

echo "==> PBXMonitorX nginx startup"
echo "    DOMAIN=$DOMAIN"

# ── Validate ─────────────────────────────────────────────────────
if [ -z "$DOMAIN" ]; then
    echo "ERROR: DOMAIN is not set. Add DOMAIN=yourdomain.com to .env"
    exit 1
fi

# ── Process template ─────────────────────────────────────────────
echo "==> Processing template..."
envsubst '$DOMAIN' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

echo "==> Generated /etc/nginx/conf.d/default.conf:"
cat /etc/nginx/conf.d/default.conf
echo ""

# ── Ensure SSL certs exist ───────────────────────────────────────
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
if [ ! -f "$CERT_DIR/fullchain.pem" ] || [ ! -f "$CERT_DIR/privkey.pem" ]; then
    echo "==> No SSL cert at $CERT_DIR — generating temporary self-signed cert"
    mkdir -p "$CERT_DIR"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$CERT_DIR/privkey.pem" \
        -out "$CERT_DIR/fullchain.pem" \
        -subj "/CN=$DOMAIN" 2>/dev/null
    echo "    WARNING: Using self-signed cert. Run certbot for a real one."
else
    echo "==> SSL cert found at $CERT_DIR"
fi

# ── Test config ──────────────────────────────────────────────────
echo "==> Testing nginx config..."
nginx -t

echo "==> Starting nginx"
exec nginx -g "daemon off;"
