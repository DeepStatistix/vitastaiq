# VitastaIQ

Data, automation and AI services from Kashmir, for local businesses, researchers and learners.

## Layout

| Path | Purpose |
|---|---|
| `site/` | Static website (plain HTML/CSS), deployed to GitHub Pages by `.github/workflows/pages.yml` |
| `site/demo/mandi/` | Mandi Intelligence dashboard built on public Agmarknet data from data.gov.in |
| `site/demo/samplesize/` | Sample Size Calculator for medical theses (five designs, power curve, methods sentence; formulas in `calc.js`) |
| `site/demo/forecast/` | Price Forecast Lab: 12-week forecasts with rolling backtests (`build_forecast.py` needs pandas, numpy, statsmodels) |
| `site/thesis/` | Landing page for medical and allied-health thesis statistics support, with an enquiry form (opens a prefilled email) |
| `site/tests/` | "Which statistical test should I use?" chooser, printable as a cheat sheet |
| `site/research/` | Research and publications page |
| `site/assets/og.png` | 1200x630 share image used in the Open Graph and Twitter tags (source: `design/og-card.html`) |
| `site/sitemap.xml`, `site/robots.txt` | Search-engine files. The URLs assume the GitHub Pages address, so update them if you add a custom domain |

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

**Daily refresh.** Fetching from GitHub's servers timed out every time, so the refresh runs on a PC instead:
`scripts/refresh_live_data.ps1` (run by a Windows scheduled task) fetches, checks the result, commits only
`site/demo/mandi/live.js` and pushes it from a dedicated clone, which triggers the Pages deploy. It keeps the existing
data if the fetch fails or returns too little. Test it safely with `-DryRun`. Logs: `%LOCALAPPDATA%\VitastaIQ\refresh.log`.

Data: Agmarknet via the Open Government Data Platform India (Government Open Data License - India).
The feed has no unit field, so the script converts apparent Rs/kg records to Rs/quintal and excludes retail
farmer markets (Uzhavar Sandhai); counts are shown on the page.
