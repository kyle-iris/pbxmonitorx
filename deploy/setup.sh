#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# PBXMonitorX — Server Setup Script
#
# Works on: Ubuntu 22.04 / 24.04 (Azure VM or DigitalOcean Droplet)
# Run as:   sudo bash setup.sh
#
# What it does:
#   1. Installs Docker + Docker Compose
#   2. Creates pbxmonitorx user
#   3. Clones your GitHub repo
#   4. Generates all secrets (.env)
#   5. Configures firewall (UFW)
#   6. Obtains Let's Encrypt SSL certificate
#   7. Starts all services
#   8. Sets up auto-renewal + log rotation
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── CONFIG (edit these or pass as env vars) ─────────────────────────────
GITHUB_REPO="${GITHUB_REPO:-}"
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
APP_DIR="/opt/pbxmonitorx"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── PRE-FLIGHT CHECKS ──────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (sudo bash setup.sh)"
fi

if [[ -z "$GITHUB_REPO" ]]; then
    read -rp "GitHub repo URL (e.g. https://github.com/you/pbxmonitorx.git): " GITHUB_REPO
fi
if [[ -z "$DOMAIN" ]]; then
    read -rp "Domain name (e.g. monitor.example.com): " DOMAIN
fi
if [[ -z "$EMAIL" ]]; then
    read -rp "Email for Let's Encrypt notifications: " EMAIL
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  PBXMonitorX Setup"
echo "  Repo:   $GITHUB_REPO"
echo "  Domain: $DOMAIN"
echo "  Email:  $EMAIL"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── 1. SYSTEM UPDATE + DEPS ────────────────────────────────────────────
log "Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    apt-transport-https ca-certificates curl gnupg lsb-release \
    git ufw fail2ban unattended-upgrades

# ── 2. INSTALL DOCKER ──────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker
    systemctl start docker
else
    log "Docker already installed"
fi

# Install Docker Compose plugin if not present
if ! docker compose version &>/dev/null; then
    log "Installing Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
fi

# ── 3. CREATE APP USER ─────────────────────────────────────────────────
if ! id -u pbxmonitorx &>/dev/null; then
    log "Creating pbxmonitorx user..."
    useradd -r -m -s /bin/bash -d /home/pbxmonitorx pbxmonitorx
    usermod -aG docker pbxmonitorx
else
    log "User pbxmonitorx already exists"
fi

# ── 4. CLONE REPO ──────────────────────────────────────────────────────
if [[ -d "$APP_DIR" ]]; then
    warn "Directory $APP_DIR already exists — pulling latest..."
    cd "$APP_DIR"
    git pull
else
    log "Cloning repository..."
    git clone "$GITHUB_REPO" "$APP_DIR"
    cd "$APP_DIR"
fi
chown -R pbxmonitorx:pbxmonitorx "$APP_DIR"

# ── 5. GENERATE SECRETS ────────────────────────────────────────────────
if [[ ! -f "$APP_DIR/.env" ]]; then
    log "Generating secrets..."
    DB_PASSWORD=$(openssl rand -hex 24)
    REDIS_PASSWORD=$(openssl rand -hex 24)
    MASTER_KEY=$(openssl rand -hex 32)
    JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n')

    cat > "$APP_DIR/.env" <<EOF
# PBXMonitorX — Generated $(date -Iseconds)
# DO NOT COMMIT THIS FILE

DB_PASSWORD=${DB_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
MASTER_KEY=${MASTER_KEY}
JWT_SECRET=${JWT_SECRET}
DOMAIN=${DOMAIN}
EMAIL=${EMAIL}
EOF

    chmod 600 "$APP_DIR/.env"
    chown pbxmonitorx:pbxmonitorx "$APP_DIR/.env"
    log "Secrets written to $APP_DIR/.env"
else
    warn ".env already exists — keeping existing secrets"
fi

# ── 6. CONFIGURE DOMAIN IN NGINX ───────────────────────────────────────
log "Configuring nginx for $DOMAIN..."
sed -i "s/REPLACE_DOMAIN/$DOMAIN/g" "$APP_DIR/deploy/nginx/conf.d/pbxmonitorx.conf"

# ── 7. FIREWALL ────────────────────────────────────────────────────────
log "Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment 'SSH'
ufw allow 80/tcp    comment 'HTTP (redirect + ACME)'
ufw allow 443/tcp   comment 'HTTPS'
ufw --force enable
log "Firewall configured: SSH(22), HTTP(80), HTTPS(443)"

# ── 8. FAIL2BAN ────────────────────────────────────────────────────────
log "Configuring fail2ban..."
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port = ssh
maxretry = 5
bantime = 3600
EOF
systemctl enable fail2ban
systemctl restart fail2ban

# ── 9. SSL CERTIFICATE ─────────────────────────────────────────────────
log "Obtaining Let's Encrypt certificate for $DOMAIN..."

# First start nginx without SSL to serve ACME challenge
# Create a temporary nginx config for initial cert
mkdir -p "$APP_DIR/deploy/nginx/conf.d.bak"
cp "$APP_DIR/deploy/nginx/conf.d/pbxmonitorx.conf" "$APP_DIR/deploy/nginx/conf.d.bak/"

# Temporary HTTP-only config for cert issuance
cat > "$APP_DIR/deploy/nginx/conf.d/pbxmonitorx.conf" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'PBXMonitorX setup in progress'; add_header Content-Type text/plain; }
}
EOF

# Start nginx temporarily
cd "$APP_DIR"
docker compose -f docker-compose.prod.yml up -d nginx

# Wait for nginx
sleep 3

# Run certbot
docker compose -f docker-compose.prod.yml run --rm certbot \
    certbot certonly --webroot -w /var/www/certbot \
    --email "$EMAIL" --agree-tos --no-eff-email \
    -d "$DOMAIN"

# Restore full SSL config
cp "$APP_DIR/deploy/nginx/conf.d.bak/pbxmonitorx.conf" "$APP_DIR/deploy/nginx/conf.d/pbxmonitorx.conf"
sed -i "s/REPLACE_DOMAIN/$DOMAIN/g" "$APP_DIR/deploy/nginx/conf.d/pbxmonitorx.conf"

log "SSL certificate obtained"

# ── 10. CREATE BACKUP DIRECTORY ─────────────────────────────────────────
mkdir -p /data/backups
chown pbxmonitorx:pbxmonitorx /data/backups

# ── 11. START ALL SERVICES ──────────────────────────────────────────────
log "Building and starting all services..."
cd "$APP_DIR"
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d

# Wait for everything to come up
log "Waiting for services to start..."
sleep 10

# Verify
docker compose -f docker-compose.prod.yml ps

# ── 12. LOG ROTATION ───────────────────────────────────────────────────
cat > /etc/logrotate.d/pbxmonitorx <<EOF
/var/log/pbxmonitorx/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
}
EOF

# ── 13. AUTO-UPDATE CRON ───────────────────────────────────────────────
cat > /etc/cron.d/pbxmonitorx-update <<'EOF'
# Check for updates daily at 4am
0 4 * * * root cd /opt/pbxmonitorx && git pull && docker compose -f docker-compose.prod.yml build --quiet && docker compose -f docker-compose.prod.yml up -d --remove-orphans
EOF

# ── DONE ────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "  ${GREEN}PBXMonitorX is running!${NC}"
echo ""
echo "  URL:        https://$DOMAIN"
echo "  API Docs:   https://$DOMAIN/api/docs"
echo "  API Health: https://$DOMAIN/api/health"
echo ""
echo "  Default login:"
echo "    Username: admin"
echo "    Password: admin (CHANGE THIS IMMEDIATELY)"
echo ""
echo "  Secrets:    $APP_DIR/.env"
echo "  Logs:       docker compose -f docker-compose.prod.yml logs -f"
echo "  Status:     docker compose -f docker-compose.prod.yml ps"
echo "═══════════════════════════════════════════════════════════"
