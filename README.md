# VitastaIQ

Data, automation and AI services from Kashmir, for local businesses, researchers and learners.

## Layout

| Path | Purpose |
|---|---|
| `site/` | Static website (plain HTML/CSS), deployed to GitHub Pages by `.github/workflows/pages.yml` |
| `site/demo/mandi/` | Mandi Intelligence dashboard built on public Agmarknet data from data.gov.in |

Internal planning documents (pricing, outreach, brand notes) are kept in a separate private repository.

## Mandi Intelligence dashboard

Open `site/demo/mandi/index.html` in a browser, or run `python -m http.server 8000 --directory site`.

To refresh the live data (standard library only; needs a free data.gov.in API key):

```
set DATA_GOV_API_KEY=<your key>
python site/demo/mandi/fetch_live.py
```

The key is read from the environment (or a `.env` passed with `--env`) and is never written to the output.
`build.py` builds the archived trend from downloaded Agmarknet CSV exports.

Data: Agmarknet via the Open Government Data Platform India (Government Open Data License - India).
The feed has no unit field, so the script converts apparent Rs/kg records to Rs/quintal and excludes retail
farmer markets (Uzhavar Sandhai); counts are shown on the page.
