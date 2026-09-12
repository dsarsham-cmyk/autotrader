# Deploying the Auto Trader to the Cloud

## ✅ Current status: already running on GitHub Actions

The bot is **already deployed and running on GitHub's cloud** via a scheduled
GitHub Actions workflow (`.github/workflows/trade.yml`). It runs every 30
minutes, checks for rebalance opportunities during US market hours, and sends
the daily Telegram report after 21:00 UTC. No PC is required.

- Repo: https://github.com/dsarsham-cmyk/autotrader
- Secrets (`ALPACA_API_KEY`, `ALPACA_API_SECRET`, `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID`) are stored as GitHub Actions secrets.
- State (`csmom_state.json`) and the trade logbook are committed back to the
  repo after each run so rebalance/report cadence persists between runs.

To trigger a manual run: GitHub → Actions → AutoTrader → "Run workflow".

---

## Alternatives (true 24/7 continuous process)

The bot is plain Python + Docker, so it can also run as a long-lived process on
any cloud. This guide covers the two easiest paths: **Railway** (easiest,
~$5/mo) and a **VPS** (cheapest, ~€4/mo).

## What you need

1. A **GitHub** account (free) — to host the code.
2. A cloud account (Railway or a VPS provider).
3. Your API keys (they're already in `.env` — you'll re-enter them as cloud
   environment variables).

## Environment variables (the only config)

| Variable | Value (from your local `.env`) |
|---|---|
| `ALPACA_API_KEY` | *(copy from `.env`)* |
| `ALPACA_API_SECRET` | *(copy from `.env`)* |
| `TELEGRAM_BOT_TOKEN` | *(copy from `.env`)* |
| `TELEGRAM_CHAT_ID` | *(copy from `.env`)* |

---

## Option A — Railway (easiest, no SSH)

1. Push this folder to a new GitHub repo:
   ```bash
   git init && git add . && git commit -m "auto trader"
   git remote add origin https://github.com/YOU/autotrader.git
   git push -u origin main
   ```
2. Go to [railway.app](https://railway.app), sign up with GitHub.
3. **New Project → Deploy from GitHub repo** → pick your repo.
   Railway auto-detects the `Dockerfile`.
4. Add the 4 environment variables above (Project → Variables).
5. Railway deploys automatically. The runner starts trading immediately.

> Railway's free tier sleeps after inactivity. For 24/7, set the service to a
> paid plan (~$5/mo) and **disable sleep** in the service settings.

---

## Option B — VPS (cheapest, ~€4/mo, full control)

Use **Hetzner** (CX22, ~€4/mo) or **DigitalOcean** ($6/mo droplet).

1. Create the VPS (Ubuntu 22.04/24.04), note its IP and root password.
2. SSH in, then:
   ```bash
   # Install Docker
   curl -fsSL https://get.docker.com | sh

   # Clone your repo (or copy the folder up)
   git clone https://github.com/YOU/autotrader.git
   cd autotrader

   # Create .env with your keys
   nano .env   # paste the 4 variables

   # Start it
   docker compose up -d --build
   ```
3. The bot is now running 24/7. Check logs with `docker compose logs -f runner`.

---

## Accessing the dashboard

⚠️ The dashboard has **no login/password** — anyone with the URL can see it.

- **Railway**: deploy the runner as the main service and rely on Telegram
  (recommended). If you also deploy `dashboard.py`, keep its URL private.
- **VPS**: leave port 8050 closed in the firewall and access it via SSH tunnel:
  ```bash
  ssh -L 8050:localhost:8050 root@YOUR_IP
  # then open http://localhost:8050 on your PC
  ```

Either way, the **daily Telegram report** works automatically — you don't need
the dashboard to stay informed.

## Verifying it's alive

The runner logs every hour. On a VPS:
```bash
docker compose logs runner | tail -20
```
You should see `CSMOM runner started ... universe=15` and periodic
`no rebalance (market_open=...)` lines while the market is closed.
