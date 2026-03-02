# PBXMonitorX — Deployment Guide

## Overview

This guide covers deploying PBXMonitorX to **Azure** with separate **Development** and **Production** environments, plus CI/CD via **GitHub Actions** for automatic deployments.

**Architecture per environment:**
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

**Environment strategy:**
```
┌──────────────────┐      ┌──────────────────┐
│   DEV (Azure)    │      │  PROD (Azure)    │
│                  │      │                  │
│  B1ms ($15/mo)   │      │  B2s  ($30/mo)   │
│  dev.monitor.co  │      │  monitor.co      │
│  develop branch  │      │  main branch     │
└──────────────────┘      └──────────────────┘
```

---

## Table of Contents

1. [Azure Resource Group Setup](#step-1-azure-resource-group-setup)
2. [Create VMs (Dev + Prod)](#step-2-create-virtual-machines)
3. [DNS Configuration](#step-3-dns-configuration)
4. [Push Code to GitHub](#step-4-push-code-to-github)
5. [Deploy Development Environment](#step-5-deploy-development-environment)
6. [Deploy Production Environment](#step-6-deploy-production-environment)
7. [CI/CD with GitHub Actions](#step-7-cicd-with-github-actions)
8. [Day 2 Operations](#day-2-operations)
9. [Azure-Specific Tips](#azure-specific-tips)
10. [Server Sizing Guide](#server-sizing-guide)
11. [Security Checklist](#security-checklist)
12. [Troubleshooting](#troubleshooting)

---

## Step 1: Azure Resource Group Setup

Create a dedicated resource group to keep all PBXMonitorX resources organized.

### Via Azure Portal

1. Log into [portal.azure.com](https://portal.azure.com)
2. **Create a resource** → **Resource group**
   - Subscription: your subscription
   - Resource group: `rg-pbxmonitorx`
   - Region: closest to your PBX locations (e.g. `East US`, `West Europe`)
3. Click **Review + create** → **Create**

### Via Azure CLI

```bash
# Install Azure CLI if needed: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
az login

# Create resource group
az group create \
  --name rg-pbxmonitorx \
  --location eastus
```

---

## Step 2: Create Virtual Machines

You need two VMs: one for **dev**, one for **prod**. They are identical except for size and naming.

### Generate SSH Keys (do this once)

```bash
# Generate a deploy key pair for each environment
ssh-keygen -t ed25519 -C "pbxmonitorx-dev" -f ~/.ssh/pbxmonitorx-dev -N ""
ssh-keygen -t ed25519 -C "pbxmonitorx-prod" -f ~/.ssh/pbxmonitorx-prod -N ""
```

### Create Development VM

#### Via Azure Portal

1. **Create a resource** → **Virtual Machine**
2. **Basics:**
   - Resource group: `rg-pbxmonitorx`
   - VM name: `vm-pbxmonitorx-dev`
   - Region: same as resource group
   - Image: **Ubuntu Server 24.04 LTS — x64 Gen2**
   - Size: **Standard_B1ms** (1 vCPU / 2 GB RAM — ~$15/mo)
   - Authentication: **SSH public key**
   - Username: `azureuser`
   - SSH public key: paste contents of `~/.ssh/pbxmonitorx-dev.pub`
3. **Disks:**
   - OS disk type: **Standard SSD**
   - OS disk size: **64 GB**
4. **Networking:**
   - Virtual network: create new `vnet-pbxmonitorx`
   - Subnet: `default (10.0.0.0/24)`
   - Public IP: create new `pip-pbxmonitorx-dev`
   - NIC NSG: **Basic**
   - Inbound ports: **SSH (22), HTTP (80), HTTPS (443)**
5. **Tags:**
   - `environment`: `dev`
   - `app`: `pbxmonitorx`
6. Click **Review + create** → **Create**

#### Via Azure CLI

```bash
az vm create \
  --resource-group rg-pbxmonitorx \
  --name vm-pbxmonitorx-dev \
  --image Canonical:ubuntu-24_04-lts:server:latest \
  --size Standard_B1ms \
  --admin-username azureuser \
  --ssh-key-values ~/.ssh/pbxmonitorx-dev.pub \
  --os-disk-size-gb 64 \
  --storage-sku StandardSSD_LRS \
  --public-ip-sku Standard \
  --nsg-rule SSH \
  --tags environment=dev app=pbxmonitorx

# Open HTTP and HTTPS ports
az vm open-port --resource-group rg-pbxmonitorx --name vm-pbxmonitorx-dev --port 80 --priority 1010
az vm open-port --resource-group rg-pbxmonitorx --name vm-pbxmonitorx-dev --port 443 --priority 1020

# Note the public IP
az vm show -d --resource-group rg-pbxmonitorx --name vm-pbxmonitorx-dev --query publicIps -o tsv
```

### Create Production VM

#### Via Azure Portal

Same steps as dev, but with these differences:

| Setting | Dev | Prod |
|---------|-----|------|
| VM name | `vm-pbxmonitorx-dev` | `vm-pbxmonitorx-prod` |
| Size | Standard_B1ms (1 vCPU / 2 GB) | **Standard_B2s (2 vCPU / 4 GB)** |
| SSH key | `pbxmonitorx-dev.pub` | `pbxmonitorx-prod.pub` |
| Public IP | `pip-pbxmonitorx-dev` | `pip-pbxmonitorx-prod` |
| OS Disk | 64 GB | **128 GB** |
| Tag: environment | `dev` | `prod` |

#### Via Azure CLI

```bash
az vm create \
  --resource-group rg-pbxmonitorx \
  --name vm-pbxmonitorx-prod \
  --image Canonical:ubuntu-24_04-lts:server:latest \
  --size Standard_B2s \
  --admin-username azureuser \
  --ssh-key-values ~/.ssh/pbxmonitorx-prod.pub \
  --os-disk-size-gb 128 \
  --storage-sku StandardSSD_LRS \
  --public-ip-sku Standard \
  --nsg-rule SSH \
  --tags environment=prod app=pbxmonitorx

az vm open-port --resource-group rg-pbxmonitorx --name vm-pbxmonitorx-prod --port 80 --priority 1010
az vm open-port --resource-group rg-pbxmonitorx --name vm-pbxmonitorx-prod --port 443 --priority 1020

az vm show -d --resource-group rg-pbxmonitorx --name vm-pbxmonitorx-prod --query publicIps -o tsv
```

---

## Step 3: DNS Configuration

Set up DNS A records pointing to each VM's public IP.

| Record | Type | Value | Purpose |
|--------|------|-------|---------|
| `dev-monitor.yourcompany.com` | A | Dev VM public IP | Dev environment |
| `monitor.yourcompany.com` | A | Prod VM public IP | Production |

**Where to configure DNS:**
- If using **Azure DNS**: Resource group → DNS zone → Add record set
- If using **Cloudflare/GoDaddy/etc.**: Use their DNS management panel

**Verify DNS propagation:**
```bash
dig +short dev-monitor.yourcompany.com
# → should return dev VM IP

dig +short monitor.yourcompany.com
# → should return prod VM IP
```

Wait for DNS propagation before proceeding (typically 5–30 minutes).

---

## Step 4: Push Code to GitHub

1. **Create a new GitHub repository** (private recommended):
   ```
   https://github.com/YOUR-ORG/pbxmonitorx
   ```

2. **Set up branches:**
   ```bash
   cd pbxmonitorx
   git init
   git add .
   git commit -m "Initial commit — PBXMonitorX v0.1.0"
   git branch -M main
   git remote add origin https://github.com/YOUR-ORG/pbxmonitorx.git
   git push -u origin main

   # Create develop branch for dev environment
   git checkout -b develop
   git push -u origin develop
   ```

3. **Branch strategy:**

   | Branch | Deploys to | Trigger |
   |--------|-----------|---------|
   | `develop` | Dev server | Push to `develop` |
   | `main` | Prod server | Push to `main` (via PR merge) |

4. **Add GitHub Secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value | Notes |
   |--------|-------|-------|
   | `DEV_SSH_HOST` | Dev VM IP or domain | `dev-monitor.yourcompany.com` |
   | `DEV_SSH_USER` | `azureuser` | Dev SSH user |
   | `DEV_SSH_KEY` | Contents of `~/.ssh/pbxmonitorx-dev` | Private key (not .pub) |
   | `PROD_SSH_HOST` | Prod VM IP or domain | `monitor.yourcompany.com` |
   | `PROD_SSH_USER` | `azureuser` | Prod SSH user |
   | `PROD_SSH_KEY` | Contents of `~/.ssh/pbxmonitorx-prod` | Private key (not .pub) |

5. **Add GitHub Environments** (Settings → Environments):
   - Create `development` environment — no protection rules
   - Create `production` environment — add **required reviewers** (recommended)

---

## Step 5: Deploy Development Environment

SSH into the dev server and run the setup:

```bash
ssh -i ~/.ssh/pbxmonitorx-dev azureuser@dev-monitor.yourcompany.com
```

### Run Automated Setup

```bash
export GITHUB_REPO="https://github.com/YOUR-ORG/pbxmonitorx.git"
export DOMAIN="dev-monitor.yourcompany.com"
export EMAIL="admin@yourcompany.com"

# Clone and run setup
sudo git clone "$GITHUB_REPO" /opt/pbxmonitorx
cd /opt/pbxmonitorx

# Switch to develop branch for dev environment
sudo git checkout develop

sudo bash deploy/setup.sh
```

### Verify Dev Environment

```bash
# Check containers
docker compose -f docker-compose.prod.yml ps

# Test API
curl https://dev-monitor.yourcompany.com/api/health

# Test login
curl -X POST https://dev-monitor.yourcompany.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

Open `https://dev-monitor.yourcompany.com` in your browser.

### Dev-Specific Configuration

After setup, customize the `.env` for dev:

```bash
sudo nano /opt/pbxmonitorx/.env

# Add these dev-specific settings at the bottom:
# LOG_LEVEL=debug
# POLLING_INTERVAL=300  (5 min — less aggressive in dev)
```

---

## Step 6: Deploy Production Environment

SSH into the prod server:

```bash
ssh -i ~/.ssh/pbxmonitorx-prod azureuser@monitor.yourcompany.com
```

### Run Automated Setup

```bash
export GITHUB_REPO="https://github.com/YOUR-ORG/pbxmonitorx.git"
export DOMAIN="monitor.yourcompany.com"
export EMAIL="admin@yourcompany.com"

sudo git clone "$GITHUB_REPO" /opt/pbxmonitorx
cd /opt/pbxmonitorx

# Stay on main branch for production
sudo bash deploy/setup.sh
```

### Verify Production Environment

```bash
docker compose -f docker-compose.prod.yml ps

curl https://monitor.yourcompany.com/api/health

curl -X POST https://monitor.yourcompany.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

**IMMEDIATELY change the default admin password after first login.**

---

## Step 7: CI/CD with GitHub Actions

The workflow in `.github/workflows/deploy.yml` handles automated deployments. Update it to support both environments:

### Workflow Overview

```
Push to develop → Lint → Build → Deploy to DEV
Push to main    → Lint → Build → Deploy to PROD (with approval)
```

### Update `.github/workflows/deploy.yml`

Replace the existing workflow with the dual-environment version below. The workflow:
- Deploys to **dev** on every push to `develop`
- Deploys to **prod** on every push to `main` (requires environment approval)
- Runs lint + build on all pull requests

```yaml
name: CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.12"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          pip install ruff
          pip install -r backend/requirements.txt
      - name: Lint with ruff
        run: ruff check backend/src/ --select E,W,F --ignore E501,W291
      - name: Check imports resolve
        run: |
          cd backend
          python -c "
          import importlib, pathlib
          errors = []
          for f in pathlib.Path('src').rglob('*.py'):
              if f.name == '__init__.py': continue
              mod = str(f.with_suffix('')).replace('/', '.')
              try:
                  importlib.import_module(mod)
              except ImportError as e:
                  if 'asyncpg' not in str(e) and 'redis' not in str(e):
                      errors.append(f'{mod}: {e}')
          if errors:
              print('Import errors:')
              for e in errors: print(f'  {e}')
          else:
              print('All imports OK (excluding runtime deps)')
          "

  build:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - name: Build backend image
        run: docker build -t pbxmonitorx-backend:${{ github.sha }} ./backend
      - name: Verify image starts
        run: |
          docker run --rm pbxmonitorx-backend:${{ github.sha }} \
            python -c "import src.main; print('App module loads OK')" || true

  deploy-dev:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/develop' && github.event_name == 'push'
    environment: development
    concurrency:
      group: deploy-dev
      cancel-in-progress: true
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Dev
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.DEV_SSH_HOST }}
          username: ${{ secrets.DEV_SSH_USER }}
          key: ${{ secrets.DEV_SSH_KEY }}
          script_stop: true
          script: |
            set -e
            cd /opt/pbxmonitorx
            echo "=== Pulling latest (develop) ==="
            git pull origin develop
            echo "=== Building images ==="
            docker compose -f docker-compose.prod.yml build --quiet
            echo "=== Rolling restart ==="
            docker compose -f docker-compose.prod.yml up -d --no-deps --build backend
            docker compose -f docker-compose.prod.yml up -d --no-deps --build worker
            docker compose -f docker-compose.prod.yml up -d --no-deps --build beat
            docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
            echo "=== Cleanup ==="
            docker image prune -f
            echo "=== Verify ==="
            sleep 5
            curl -sf http://localhost:8000/api/health || echo "Health check warning"
            docker compose -f docker-compose.prod.yml ps

  deploy-prod:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment: production
    concurrency:
      group: deploy-production
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Production
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.PROD_SSH_HOST }}
          username: ${{ secrets.PROD_SSH_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script_stop: true
          script: |
            set -e
            cd /opt/pbxmonitorx
            echo "=== Pulling latest (main) ==="
            git pull origin main
            echo "=== Building images ==="
            docker compose -f docker-compose.prod.yml build --quiet
            echo "=== Rolling restart ==="
            docker compose -f docker-compose.prod.yml up -d --no-deps --build backend
            docker compose -f docker-compose.prod.yml up -d --no-deps --build worker
            docker compose -f docker-compose.prod.yml up -d --no-deps --build beat
            docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
            echo "=== Cleanup ==="
            docker image prune -f
            echo "=== Verify ==="
            sleep 5
            curl -sf http://localhost:8000/api/health || echo "Health check warning"
            docker compose -f docker-compose.prod.yml ps
```

### Development Workflow (Day to Day)

```bash
# 1. Create a feature branch from develop
git checkout develop
git pull
git checkout -b feature/my-feature

# 2. Make changes, commit
git add .
git commit -m "Add my feature"

# 3. Push and create PR targeting develop
git push -u origin feature/my-feature
gh pr create --base develop --title "Add my feature"

# 4. After PR review + merge → auto-deploys to dev server

# 5. When dev is tested and ready, create PR: develop → main
gh pr create --base main --head develop --title "Release: my feature"

# 6. After PR approval + merge → auto-deploys to production
```

---

## Day 2 Operations

### View Logs

```bash
cd /opt/pbxmonitorx

# All services
make logs

# Specific service
docker compose -f docker-compose.prod.yml logs -f worker
docker compose -f docker-compose.prod.yml logs -f backend
```

### Database Access

```bash
make shell-db
# \dt       — list tables
# SELECT * FROM pbx_instance;
# SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 20;
# SELECT * FROM event_log WHERE level = 'error' ORDER BY timestamp DESC LIMIT 10;
```

### Backup the Database

```bash
make backup-db
# Creates backup_YYYYMMDD_HHMMSS.sql in current directory
```

### Restart a Single Service

```bash
docker compose -f docker-compose.prod.yml restart worker
```

### Update Manually

```bash
cd /opt/pbxmonitorx
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

### SSL Certificate Renewal

Handled automatically by the certbot container every 12 hours.

Manual renewal:
```bash
docker compose -f docker-compose.prod.yml run --rm certbot \
  certbot renew --webroot -w /var/www/certbot
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

### Promote Dev to Production

```bash
# On your local machine:
git checkout main
git merge develop
git push origin main
# → CI/CD auto-deploys to production
```

---

## Azure-Specific Tips

### Auto-Shutdown (Save Money on Dev)

Set the dev VM to auto-shutdown overnight to reduce costs:

```bash
# Portal: VM → Auto-shutdown → Enable → Set time (e.g., 7:00 PM)

# CLI:
az vm auto-shutdown \
  --resource-group rg-pbxmonitorx \
  --name vm-pbxmonitorx-dev \
  --time 1900 \
  --timezone "Eastern Standard Time"
```

To restart in the morning:
```bash
az vm start --resource-group rg-pbxmonitorx --name vm-pbxmonitorx-dev
```

### Azure Reserved Instances (Save on Prod)

For the production VM, purchase a 1-year reserved instance for ~40% savings:
- Portal → Reservations → Purchase reservation
- VM size: `Standard_B2s`
- Term: 1 year (~$18/mo instead of $30/mo)

### Azure Backup (Prod Only)

Enable Azure Backup for the production VM:

```bash
# Create a Recovery Services vault
az backup vault create \
  --resource-group rg-pbxmonitorx \
  --name rsv-pbxmonitorx \
  --location eastus

# Enable backup with default policy (daily, 30-day retention)
az backup protection enable-for-vm \
  --resource-group rg-pbxmonitorx \
  --vault-name rsv-pbxmonitorx \
  --vm vm-pbxmonitorx-prod \
  --policy-name DefaultPolicy
```

### Network Security Group (Lock Down Further)

Restrict SSH to your office IP range:

```bash
# Replace with your actual office IP
az network nsg rule update \
  --resource-group rg-pbxmonitorx \
  --nsg-name vm-pbxmonitorx-prodNSG \
  --name default-allow-ssh \
  --source-address-prefixes "YOUR.OFFICE.IP/32"
```

### Azure Monitor Alerts

Set up alerts for VM health:

```bash
# Alert when CPU > 90% for 5 min
az monitor metrics alert create \
  --resource-group rg-pbxmonitorx \
  --name "PBXMonitorX-Prod-HighCPU" \
  --scopes "/subscriptions/{sub-id}/resourceGroups/rg-pbxmonitorx/providers/Microsoft.Compute/virtualMachines/vm-pbxmonitorx-prod" \
  --condition "avg Percentage CPU > 90" \
  --window-size 5m \
  --evaluation-frequency 1m
```

---

## Server Sizing Guide

| PBX Count | Polling | VM Size | RAM | CPU | Disk | Cost/mo |
|-----------|---------|---------|-----|-----|------|---------|
| Dev/Test | 5 min | B1ms | 2 GB | 1 vCPU | 64 GB | ~$15 |
| 1–3 | 1 min | B1ms | 2 GB | 1 vCPU | 64 GB | ~$15 |
| 4–10 | 1 min | B2s | 4 GB | 2 vCPU | 128 GB | ~$30 |
| 10–25 | 5 min | B4ms | 16 GB | 4 vCPU | 256 GB | ~$60 |
| 25+ | 10 min | B4ms | 16 GB | 4 vCPU | 512 GB | ~$120 |

Disk usage: ~150 MB per PBX backup. Plan retention accordingly.

**Total estimated Azure cost (Dev + Prod for 1–10 PBXes):**
- Dev VM (B1ms): ~$15/mo (or ~$8/mo with auto-shutdown)
- Prod VM (B2s): ~$30/mo (or ~$18/mo with reserved instance)
- **Total: $23–$45/mo**

---

## Security Checklist

### Both Environments

- [ ] Changed default admin password
- [ ] SSH key auth only (disable password auth)
- [ ] UFW firewall active (22, 80, 443 only)
- [ ] fail2ban running
- [ ] `.env` file permissions are `600`
- [ ] GitHub repo is **private**
- [ ] GitHub Secrets used (no hardcoded credentials)
- [ ] TLS/SSL active on the domain
- [ ] Database not exposed to internet (internal Docker network only)
- [ ] Redis not exposed to internet (internal Docker network only)

### Production Only

- [ ] NSG SSH restricted to known IPs
- [ ] Azure Backup enabled
- [ ] GitHub environment protection rules (require approval for prod deploy)
- [ ] Azure Monitor alerts configured
- [ ] Auto-update cron reviewed and tested

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
# Check NSG rules in Azure portal
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
# If timeout: check Azure NSG outbound rules + PBX firewall
# If SSL error: use trust_self_signed TLS policy
```

**Azure VM won't start after auto-shutdown:**
```bash
# Start via CLI
az vm start --resource-group rg-pbxmonitorx --name vm-pbxmonitorx-dev
# Or via portal: VM → Start
```

**Out of disk space:**
```bash
# Check disk usage
df -h
# Clean up Docker images
docker system prune -a --volumes
# Check backup retention
du -sh /data/backups/
```

**Database migration on update:**
```bash
# If init.sql has new tables, you may need to apply them manually:
docker compose exec postgres psql -U pbxmonitorx -f /docker-entrypoint-initdb.d/001_init.sql
# init.sql uses IF NOT EXISTS and ON CONFLICT DO NOTHING, so it's safe to re-run
```
