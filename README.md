# 🌍 Country Portfolio Draft

Build the best $100,000 paper portfolio using only stocks from **one country per week**, then track all of them on a live public leaderboard. A sneaky way to teach global markets.

**Opening season:** 🇰🇷 Korea · 🇸🇦 Saudi Arabia · 🇮🇳 India · 🇺🇸 United States

## How it works

- Each country gets **$100,000** of paper money, split into six buckets:
  20% tech · 20% boring · 20% commodity/crops · 20% consumer · 10% banking · 10% wildcard.
- Prices come from **Yahoo Finance** using each stock's *local exchange* ticker
  (`.KS` Korea, `.SR` Saudi, `.NS` India), so even niche local companies work —
  no need to limit picks to US-listed ADRs.
- Local currencies (KRW, SAR, INR) are auto-converted to USD so every portfolio
  sits on one comparable leaderboard.

## The draft picks
- [`korea picks.md`](korea%20picks.md)
- [`saudi picks.md`](saudi%20picks.md)
- [`india picks.md`](india%20picks.md)
- [`usa picks.md`](usa%20picks.md)

## Files

| File | What it is |
|------|-----------|
| `portfolios.json` | The roster: each country's 6 picks, tickers, target weights. **Edit this to change picks.** |
| `engine.py` | Pulls live prices + FX, locks share counts on first run, re-prices every run, writes `data.json`. |
| `holdings.json` | The locked positions (fixed share counts + buy-in prices). Created on first run — **do not delete** unless you want to re-lock. |
| `data.json` | Current values/returns. Generated output — the dashboard reads this. |
| `index.html` | The live dashboard / leaderboard. |
| `.github/workflows/update.yml` | Re-runs the engine **hourly** and commits fresh data. |

## Run it locally

```bash
pip install -r requirements.txt
python3 engine.py            # locks on first run, then re-prices
python3 -m http.server 8765  # then open http://localhost:8765
```

## Deploy the live public link (free)

1. Create a **public** GitHub repo and push this folder to it.
2. **Settings → Pages →** Source: *Deploy from a branch* → `main` / `/root`. Your
   dashboard goes live at `https://<you>.github.io/<repo>/`.
3. **Settings → Actions → General →** Workflow permissions: *Read and write*.
4. The workflow then runs **hourly** and auto-commits updated prices. (Trigger a
   first run manually under the **Actions** tab → *Update portfolio prices* → *Run workflow*.)

## Adding a new country each week

1. Add a new country block to `portfolios.json` (same shape as the others).
2. Commit & push. On the next engine run the new portfolio is locked **as if bought
   at the common `start_date` (2026-07-27) closing price** — backfilled from history —
   so every country races from the same fair baseline. Existing locks are untouched.
3. A country added later therefore appears with performance already accrued since
   2026-07-27. (To instead start each country on its own air date, give it its own
   `lock_date`; the fixed-baseline behavior is the default.)

---
*Paper money for education/entertainment. Not investment advice.*
