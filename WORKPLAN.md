# WORKPLAN — brixels

**Status**: ~80% complete. GitHub mirror ready. R2 storage integrated. Streamlit Cloud UNBLOCKED.
**Critical path**: Deploy → print size UI → Prodigi integration → first revenue.
**Last commit**: 2025-12-20 (COG sampler). Env updated 2026-04-20.

---

## This sprint (Apr 24 – May 1)

- [ ] **BRX-7** ~1hr: Deploy to Streamlit Cloud — connect `github.com/krshI27/brixels`, verify R2 loads (`brixels_world.gpkg`), test map renders
- [ ] **BRX-3** ~1hr: Add print size selector in sidebar — A4 / A3 / A2 / square; store in session_state; needed before Prodigi integration

## Next sprint

- [ ] **BRX-EXPORT** ~1hr: Implement print export — render map at A4 resolution (2480×3508px / 300dpi); export as JPEG via `PIL.Image.save(buf, "JPEG", dpi=(300,300))`; verify output size satisfies Prodigi spec before wiring Prodigi
- [ ] **BRX-UPLOAD** ~30min: Upload print PNG to R2 public bucket (`krshi27-prints/`) via boto3 → return public URL; this URL passes to Prodigi as the asset
- [ ] **BRX-8** ~1.5hr: Prodigi order flow — `POST https://api.prodigi.com/v4.0/orders` with `GLOBAL-FAP-11.7X8.3` (A4) / `GLOBAL-FAP-16.5X11.7` (A3); use `PRODIGI_API_KEY` from `.streamlit/secrets.toml`; return order ID
- [ ] **BRX-9** ~1hr: Checkout UI — name, address, email form; submit triggers BRX-UPLOAD → BRX-8 in sequence; show Prodigi order confirmation
- [ ] **ZV1-4** ~1hr: Add `?preset=` URL loader (see pattern below) — encode lat/lon/zoom/style as JSON; add `key=` to all widgets; test QR round-trip
- [ ] **BRX-10** ~1hr: Create 5 showcase presets — specific locations, strong output; save as `presets/zine-vol1-*.json`

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
