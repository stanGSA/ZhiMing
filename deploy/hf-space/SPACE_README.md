---
title: ZhiMing — Verifiable Multi-Agent Divination Demo
emoji: 🧭
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: agpl-3.0
short_description: Offline deterministic BaZi, Western Natal Chart & Tarot Agent demo
---

# ZhiMing (知命) — Offline Demo Space

This Hugging Face Space runs **ZhiMing** in **pure offline demo mode** (`--demo-only`, zero LLM API keys):

- **Deterministic BaZi (Four Pillars):** Solar-term pillars, Ten Gods, hidden stems, NaYin, WuXing counts, and 10-year Dayun.
- **Deterministic Western Natal Chart:** Swiss Ephemeris planetary longitudes, Placidus houses, four angles, and exact aspects (cross-verified against NASA JPL DE440s).
- **Deterministic Kangxi Name Strokes (Wuge)** & **Daily Almanac**.
- **Interactive Tarot Demo:** Reproducible SHA256-shuffled 78-card spread with rule-based demo interpretation.

For full LLM-powered readings, visit the live site at [https://zhiming.mom](https://zhiming.mom).

**Source code (AGPL-3.0-or-later):** https://github.com/stanGSA/ZhiMing
