# Hugging Face Spaces — Pure Offline Demo Deployment

This directory provides a self-contained **Docker** setup to deploy **ZhiMing (知命)** on [Hugging Face Spaces](https://huggingface.co/spaces) in **pure offline demo mode** (`--demo-only`).

- **Zero API keys / zero LLM cost:** Every session is locked to `provider="demo"`. Visitors can calculate real BaZi Four Pillars, Western Natal Charts (Swiss Ephemeris), Kangxi Name Strokes, Daily Almanacs, and interactive Tarot draws with zero paid API calls.
- **Baked-in verified data:** `scripts.fetch_data` (~70 MB, SHA256-verified) and `knowledge.build` run during `docker build`, so container startup takes seconds.
- **Iframe-safe security:** Uses `--allow-host "*.hf.space"` and `--embed-ancestor https://huggingface.co --embed-ancestor https://*.hf.space` so session cookies (`SameSite=None; Secure`) and CSP `frame-ancestors` work inside Hugging Face Spaces without weakening CSRF/Origin checks.

---

## Option 1: Local Docker Build & Smoke Test

Run from the **repository root** (not inside `deploy/hf-space/`):

```bash
docker build -f deploy/hf-space/Dockerfile -t zhiming-hf-demo .
docker run --rm -p 7860:7860 zhiming-hf-demo
```

Then open http://127.0.0.1:7860 (or check http://127.0.0.1:7860/healthz).

> Note: When testing locally over plain `http://127.0.0.1:7860`, browsers ignore `Secure` cookies on non-HTTPS origins other than `localhost`; for local plain-HTTP smoke tests without iframe headers, override the command:
> `docker run --rm -p 7860:7860 zhiming-hf-demo python web.py --host 0.0.0.0 --port 7860 --demo-only`

---

## Option 2: Deploy to Hugging Face Spaces

1. Create a new Space on Hugging Face (`https://huggingface.co/new-space`):
   - **SDK:** `Docker` (Blank template)
   - **Hardware:** `CPU basic (2 vCPU, 16 GB RAM)` — free tier is plenty.
   - **License:** `agpl-3.0`
2. Clone your Space repo and copy the ZhiMing source + Space metadata:

   ```bash
   git clone https://huggingface.co/spaces/<your-hf-user>/ZhiMing-Demo hf-space
   # Copy repo files (excluding .git, .venv, data, runs, reports, docs/verification)
   cp deploy/hf-space/Dockerfile hf-space/Dockerfile
   cp deploy/hf-space/SPACE_README.md hf-space/README.md
   ```

   *(Or point a GitHub Actions workflow to sync the repo root + `deploy/hf-space/Dockerfile` as `Dockerfile` and `deploy/hf-space/SPACE_README.md` as `README.md` to your Space remote.)*
3. Push to Hugging Face Spaces:

   ```bash
   cd hf-space
   git add -A
   git commit -m "chore: deploy ZhiMing offline demo Space"
   git push
   ```

4. Wait ~2–4 minutes for the Docker build (fetches ~70 MB ephemeris/GeoNames/Unihan data once and caches the layer). Your Space will boot on port `7860` and pass `/healthz`.

---

## AGPL-3.0 Compliance Reminder

Because Swiss Ephemeris (`pyswisseph` + `sepl_18.se1` / `semo_18.se1`) is AGPL-3.0 licensed, any public Hugging Face Space must keep its Space repository public (or link prominently to the exact corresponding source code). `SPACE_README.md` and the web UI footer + `/privacy` page include the source link by default.
