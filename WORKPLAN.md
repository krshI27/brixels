# WORKPLAN — brixels

**Status**: DEPLOYED on Streamlit Cloud (2026-04-25). R2 storage integrated. No Prodigi code yet.
**Critical path**: Verify R2 secrets on Cloud → print size UI → Prodigi integration → first revenue.
**⚠️ Verify**: R2 auth secrets (`CLOUDFLARE_S3_API` or `R2_ACCESS_ID`+`R2_SECRET_ACCESS_KEY`+`R2_ACCOUNT_ID`) must be in Streamlit Cloud secrets dashboard — local secrets.toml only has bucket name + Prodigi key.
**Last commit**: fix: remove unused import + src/__init__.py (2026-04-25).

---

## Active priorities (2026-04-25 — Path A focus, revenue deferred)

### Path A: Zine Vol.1 preset rollout (do first — unblocks zine pipeline)

- [ ] **BRX-R2-VERIFY** ~15min: Open live Cloud URL, confirm map data loads from R2 (if blank/error → check R2 secrets in Cloud dashboard). Blocker for everything below.
- [ ] **ZV1-4** ~1hr: Add `?preset=` URL loader (see pattern below) — encode lat/lon/zoom/style as JSON; add `key=` to all widgets matching params; test QR round-trip
- [ ] **ZV1-preset-brixels** ~30min: Pick 1–2 hero locations → save params as `presets/zine-vol1-*.json`

### Revenue path (deferred until Zine Vol.1 produced)

- [x] **BRX-7**: Deployed to Streamlit Cloud (2026-04-25)
- [ ] **BRX-3** ~1hr: Print size selector in sidebar — A4 / A3 / A2 / square; store in session_state
- [ ] **BRX-EXPORT** ~1hr: Print export — render map at A4 resolution (2480×3508px / 300dpi); export as JPEG via `PIL.Image.save(buf, "JPEG", dpi=(300,300))`; verify ≥ Prodigi spec
- [ ] **BRX-UPLOAD** ~30min: Upload print PNG to R2 public bucket (`krshi27-prints/`) via boto3 → return public URL
- [ ] **BRX-8** ~1.5hr: Prodigi order flow — `POST https://api.prodigi.com/v4.0/orders` with `GLOBAL-FAP-11.7X8.3` (A4) / `GLOBAL-FAP-16.5X11.7` (A3); `PRODIGI_API_KEY` from `.streamlit/secrets.toml`
- [ ] **BRX-9** ~1hr: Checkout UI — name/address/email form; submit triggers BRX-UPLOAD → BRX-8
- [ ] **BRX-10** ~1hr: 5 showcase presets — strong locations; save as `presets/showcase-*.json`

## Preset loader pattern (Streamlit)

```python
import json
import streamlit as st

_raw = st.query_params.get("preset")
if _raw:
    try:
        _p = json.loads(_raw)
        for k, v in _p.get("params", {}).items():
            st.session_state.setdefault(k, v)
    except (json.JSONDecodeError, KeyError):
        pass
# all widgets need key= matching the params keys, e.g. st.slider("zoom", ..., key="zoom")
```

## Decisions needed

- Print DPI: verify current map renderer output size — must be ≥2480×3508px for A4@300dpi
- Pricing: A4 Prodigi cost ~€5–8 → suggest retail €18–25
- Preset encoding: lat/lon/zoom/style/colorscheme all go in `params{}` as flat JSON

## Notes

- R2 credentials + Prodigi API key both in `.streamlit/secrets.toml` (gitignored)
- Prodigi docs: https://www.prodigi.com/print-api/docs/
- See `krshi27-scribe/WORKPLAN.md` for the shared `upload_to_r2()` + `create_prodigi_order()` pattern — same pattern applies here
- Dockerfile + docker-compose.yml useful for local Prodigi integration testing
