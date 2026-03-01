# PBXMonitorX — Deployment Guide

## Overview

This guide covers deploying PBXMonitorX to a fresh Ubuntu server on **Azure** or **DigitalOcean**, with CI/CD via **GitHub Actions** for automatic deployments on push to `main`.

**Architecture:**
```
GitHub (code) → GitHub Actions (build) → SSH → Server
                                                │
                     ┌──────────────────────────┘
                     ▼
        ┌─── nginx (443/TLS) ───┐
        │                       │
        ▼                       ▼
    FastAPI (8000)          static files
        │
   ┌────┼────────┐
   ▼    ▼        ▼
 Celery Redis  PostgreSQL
 Worker
```

---

## Step 1: Create the Server

### Option A: DigitalOcean

1. Log into [cloud.digitalocean.com](https://cloud.digitalocean.com)
2. **Create Droplet:**
   - Image: **Ubuntu 24.04 LTS**
   - Plan: **Basic → Regular → $12/mo** (2 GB RAM / 1 vCPU / 50 GB disk)
     - For 5+ PBX instances: $24/mo (4 GB RAM)
   - Region: closest to your PBX locations
   - Authentication: **SSH key** (strongly recommended)
   - Hostname: `pbxmonitorx`
3. Note the **IP address** after creation
4. Point your **DNS**: `monitor.yourcompany.com` → A record → droplet IP

### Option B: Azure

1. Log into [portal.azure.com](https://portal.azure.com)
2. **Create Virtual Machine:**
   - Image: **Ubuntu Server 24.04 LTS**
   - Size: **Standard_B2s** (2 vCPU / 4 GB RAM — $30/mo)
     - B1ms (1 vCPU / 2 GB) works for ≤3 PBX instances
   - Authentication: **SSH public key**
   - Inbound ports: **SSH (22), HTTP (80), HTTPS (443)**
   - OS Disk: **Standard SSD, 64 GB**
3. After deployment, note the **Public IP**
4. In **Networking**, verify NSG rules allow ports 22, 80, 443
5. Point DNS: `monitor.yourcompany.com` → A record → VM IP

### DNS Setup (both providers)

Wait for DNS propagation before proceeding. Verify:
```bash
dig +short monitor.yourcompany.com
# Should return your server IP
```

---

## Step 2: Push Code to GitHub

1. **Create a new GitHub repository** (private recommended):
   ```
   https://github.com/YOUR-ORG/pbxmonitorx
   ```

2. **Initialize and push:**
   ```bash
   cd pbxmonitorx
   git init
   git add .
   git commit -m "Initial commit — PBXMonitorX v0.1.0"
   git branch -M main
   git remote add origin https://github.com/YOUR-ORG/pbxmonitorx.git
   git push -u origin main
   ```

3. **Add GitHub Secrets** for CI/CD (Settings → Secrets → Actions):

   | Secret | Value | Example |
   |--------|-------|---------|
   | `SSH_HOST` | Server IP or domain | `monitor.yourcompany.com` |
   | `SSH_USER` | SSH username | `root` or `pbxmonitorx` |
   | `SSH_KEY` | Private SSH key contents | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

4. **Create a deploy key** (recommended over personal SSH keys):
   ```bash
   ssh-keygen -t ed25519 -C "pbxmonitorx-deploy" -f deploy_key -N ""
   # Copy deploy_key.pub to server's ~/.ssh/authorized_keys
   # Copy deploy_key (private) to GitHub Secret SSH_KEY
   ```

---

## Step 3: Run the Setup Script

SSH into your server and run the automated setup:

```bash
ssh root@monitor.yourcompany.com
```

```bash
# One-liner setup
export GITHUB_REPO="https://github.com/YOUR-ORG/pbxmonitorx.git"
export DOMAIN="monitor.yourcompany.com"
export EMAIL="admin@yourcompany.com"

curl -sSL https://raw.githubusercontent.com/YOUR-ORG/pbxmonitorx/main/deploy/setup.sh | sudo bash
```

**Or step by step:**
```bash
git clone https://github.com/YOUR-ORG/pbxmonitorx.git /opt/pbxmonitorx
cd /opt/pbxmonitorx
sudo bash deploy/setup.sh
```

The script will:
- Install Docker + Docker Compose
- Generate all secrets (`.env`)
- Configure UFW firewall
- Set up fail2ban
- Obtain Let's Encrypt SSL certificate
- Build and start all 6 containers
- Configure auto-renewal + log rotation

---

## Step 4: Verify

After setup completes:

```bash
# Check all containers are running
docker compose -f docker-compose.prod.yml ps

# Expected output:
#   postgres  — running (healthy)
#   redis     — running (healthy)
#   backend   — running
#   worker    — running
#   beat      — running
#   nginx     — running
#   certbot   — running
```

```bash
# Test API
curl https://monitor.yourcompany.com/api/health
# {"status":"ok","version":"0.1.0"}
```

```bash
# Test login
curl -X POST https://monitor.yourcompany.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
# Returns JWT token
```

Open `https://monitor.yourcompany.com` in your browser.

**⚠️ IMMEDIATELY change the default admin password.**

---

## Step 5: CI/CD — Automatic Deployments

With GitHub Secrets configured, every push to `main` will:

1. **Lint** Python code with ruff
2. **Build** Docker image and smoke test
3. **Deploy** via SSH:
   - Pull latest code
   - Rebuild images
   - Rolling restart (zero nginx downtime)
   - Health check verification

To deploy manually from the server:
```bash
cd /opt/pbxmonitorx
make deploy
```

---

## Day 2 Operations

### View logs
```bash
cd /opt/pbxmonitorx

# All services
make logs

# Specific service
docker compose -f docker-compose.prod.yml logs -f worker
docker compose -f docker-compose.prod.yml logs -f backend
```

### Database access
```bash
make shell-db
# \dt       — list tables
# SELECT * FROM pbx_instance;
# SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 20;
```

### Backup the database itself
```bash
make backup-db
# Creates backup_20260218_143000.sql in current directory
```

### Restart a single service
```bash
docker compose -f docker-compose.prod.yml restart worker
```

### Update to latest version
```bash
cd /opt/pbxmonitorx
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

### SSL certificate renewal
Handled automatically by the certbot container every 12 hours.
Manual renewal:
```bash
docker compose -f docker-compose.prod.yml run --rm certbot \
  certbot renew --webroot -w /var/www/certbot
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

---

## Server Sizing Guide

| PBX Count | Polling | RAM | CPU | Disk | Cost/mo |
|-----------|---------|-----|-----|------|---------|
| 1–3 | 1 min | 2 GB | 1 vCPU | 50 GB | $12 (DO) / $15 (Azure B1ms) |
| 4–10 | 1 min | 4 GB | 2 vCPU | 80 GB | $24 (DO) / $30 (Azure B2s) |
| 10–25 | 5 min | 8 GB | 4 vCPU | 160 GB | $48 (DO) / $60 (Azure B4ms) |
| 25+ | 10 min | 16 GB | 4 vCPU | 320 GB | $96 (DO) / $120 (Azure B4ms) |

Disk usage: ~150 MB per PBX backup. Plan accordingly for retention.

---

## Security Checklist

- [ ] Changed default admin password
- [ ] SSH key auth only (disable password auth)
- [ ] UFW firewall active (22, 80, 443 only)
- [ ] fail2ban running
- [ ] `.env` file permissions are `600`
- [ ] GitHub repo is **private**
- [ ] GitHub Secrets used (no hardcoded credentials)
- [ ] TLS/SSL active on the domain
- [ ] Database not exposed to internet (internal network only)
- [ ] Redis not exposed to internet (internal network only)

---

## Troubleshooting

**Container won't start:**
```bash
docker compose -f docker-compose.prod.yml logs backend
# Check for MASTER_KEY assertion error → regenerate .env
```

**SSL certificate fails:**
```bash
# Verify DNS resolves to this server
dig +short monitor.yourcompany.com
# Verify port 80 is open
curl http://monitor.yourcompany.com/.well-known/acme-challenge/test
```

**Polling not working:**
```bash
docker compose -f docker-compose.prod.yml logs worker
# Look for "Poll cycle" messages
# If no polls: check beat is running, check PBX is_enabled=true
```

**Can't connect to PBX:**
```bash
# From the server, test HTTPS to PBX
curl -k https://your-pbx.example.com:5001
# If timeout: firewall between server and PBX
# If SSL error: use trust_self_signed TLS policy
```
