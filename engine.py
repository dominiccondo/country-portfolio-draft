#!/usr/bin/env python3
"""
Country Portfolio Draft — price engine.

- On first run it LOCKS each portfolio: pulls current prices + USD FX rates,
  converts to USD, and computes exact (fractional) share counts so every pick
  hits its dollar target inside a $100,000 book. Saved to holdings.json.
- On every run it RE-PRICES the locked share counts and also RECONSTRUCTS each
  portfolio's daily value history since the lock date (from historical closes),
  then writes data.json (consumed by index.html).

Pure standard library + certifi. Data source: Yahoo Finance via local-exchange
tickers (.KS / .SR / .NS) and FX pairs (XXX=X). One request per symbol returns
both the live price and the daily history.
"""
import json
import os
import ssl
import time
import urllib.request
from datetime import datetime, timezone, date, timedelta

# Days of context to show BEFORE the lock date on the chart. Set to 0 so each
# portfolio's performance line begins on its draft-lock date.
CHART_LOOKBACK_DAYS = 0

HERE = os.path.dirname(os.path.abspath(__file__))
PORTFOLIOS = os.path.join(HERE, "portfolios.json")
HOLDINGS = os.path.join(HERE, "holdings.json")
DATA_OUT = os.path.join(HERE, "data.json")

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_default_context()

UA = {"User-Agent": "Mozilla/5.0 (compatible; CountryPortfolioDraft/1.0)"}


def fetch_series(symbol, retries=4):
    """Return (live_price, currency, {date: close}) for a Yahoo symbol."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        "?range=1y&interval=1d"
    )
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                res = json.load(r)["chart"]["result"][0]
            meta = res["meta"]
            price = meta.get("regularMarketPrice")
            currency = meta.get("currency")
            hist = {}
            ts = res.get("timestamp") or []
            closes = res["indicators"]["quote"][0].get("close") or []
            for t, c in zip(ts, closes):
                if c is None:
                    continue
                d = datetime.fromtimestamp(t, timezone.utc).date().isoformat()
                hist[d] = float(c)
            if price is None:
                raise ValueError("no price")
            return float(price), currency, hist
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {symbol}: {last}")


def gather(portfolios):
    """One request per ticker + per FX currency. Returns quotes + fx maps."""
    quotes, fx = {}, {}
    for c in portfolios["countries"]:
        for h in c["holdings"]:
            t = h["ticker"]
            price, cur, hist = fetch_series(t)
            quotes[t] = {"price": price, "currency": cur, "hist": hist}
    currencies = {q["currency"] for q in quotes.values() if q["currency"] != "USD"}
    for cur in currencies:
        price, _, hist = fetch_series(f"{cur}=X")
        fx[cur] = {"rate": price, "hist": hist}
    return quotes, fx


def rate_now(currency, fx):
    return 1.0 if currency == "USD" else fx[currency]["rate"]


def ffill(hist, date, fallback):
    """Value in `hist` on `date`, else the most recent prior value, else fallback."""
    if date in hist:
        return hist[date]
    prior = [d for d in hist if d <= date]
    return hist[max(prior)] if prior else fallback


def lock_positions(portfolios, quotes, fx, existing):
    """Lock any ticker not already locked, as if bought at the series' common
    start date (portfolios.json `start_date`) at that day's closing price.
    Every portfolio — including ones added later — shares the same July-27 basis,
    so the leaderboard is a fair, apples-to-apples race. Existing locks are kept."""
    capital = portfolios["starting_capital"]
    start_date = portfolios["start_date"]
    positions = dict(existing)
    newly = []
    for c in portfolios["countries"]:
        for h in c["holdings"]:
            t = h["ticker"]
            if t in positions:
                continue
            q = quotes[t]
            cur = q["currency"]
            # exact close on the start date if the daily bar exists (true for any
            # country added later); on the start date itself the bar may not have
            # posted yet, so fall back to the live price (= that day's close after
            # the market closes), never to a stale earlier day.
            price_local = q["hist"].get(start_date, q["price"])
            rate = 1.0 if cur == "USD" else fx[cur]["hist"].get(start_date, fx[cur]["rate"])
            price_usd = price_local / rate
            target = h["weight"] * capital
            positions[t] = {
                "shares": target / price_usd,
                "lock_price_local": price_local,
                "lock_price_usd": price_usd,
                "currency": cur,
                "cost_usd": target,
                "lock_date": start_date,
            }
            newly.append(t)
    return positions, newly


def country_history(country, positions, quotes, fx, start_date, capital, now_iso, now_value):
    """Daily value series for the locked basket, incl. pre-lock context, plus a live point."""
    chart_start = (date.fromisoformat(start_date) - timedelta(days=CHART_LOOKBACK_DAYS)).isoformat()
    dates = set()
    for h in country["holdings"]:
        for d in quotes[h["ticker"]]["hist"]:
            if d >= chart_start:
                dates.add(d)
    series = []
    for d in sorted(dates):
        value = 0.0
        for h in country["holdings"]:
            t = h["ticker"]
            pos = positions[t]
            cur = pos["currency"]
            close = ffill(quotes[t]["hist"], d, pos["lock_price_local"])
            rate = 1.0 if cur == "USD" else ffill(fx[cur]["hist"], d, fx[cur]["rate"])
            value += pos["shares"] * (close / rate)
        series.append({"t": d, "value_usd": round(value, 2),
                       "return_pct": round((value / capital - 1) * 100, 2),
                       "pre": d < start_date})
    # append the live intraday point
    series.append({"t": now_iso, "value_usd": round(now_value, 2),
                   "return_pct": round((now_value / capital - 1) * 100, 2),
                   "pre": False})
    return series


def build_data(portfolios, holdings, quotes, fx):
    capital = portfolios["starting_capital"]
    positions = holdings["positions"]
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = []
    for c in portfolios["countries"]:
        rows, total = [], 0.0
        for h in c["holdings"]:
            t = h["ticker"]
            pos, q = positions[t], quotes[t]
            price_usd = q["price"] / rate_now(q["currency"], fx)
            value = pos["shares"] * price_usd
            cost = pos["cost_usd"]
            total += value
            rows.append({
                "bucket": h["bucket"], "company": h["company"], "ticker": t,
                "currency": q["currency"], "shares": round(pos["shares"], 4),
                "lock_price_usd": round(pos["lock_price_usd"], 4),
                "price_usd": round(price_usd, 4),
                "value_usd": round(value, 2), "cost_usd": round(cost, 2),
                "gain_usd": round(value - cost, 2),
                "return_pct": round((value / cost - 1) * 100, 2),
            })
        cstart = min(positions[h["ticker"]]["lock_date"] for h in c["holdings"])
        hist = country_history(c, positions, quotes, fx, cstart, capital, now_iso, total)
        out.append({
            "code": c["code"], "name": c["name"], "exchange": c["exchange"],
            "start_date": cstart,
            "value_usd": round(total, 2), "cost_usd": capital,
            "gain_usd": round(total - capital, 2),
            "return_pct": round((total / capital - 1) * 100, 2),
            "holdings": rows, "history": hist,
        })
    out.sort(key=lambda x: x["return_pct"], reverse=True)
    global_start = min(p["lock_date"] for p in positions.values())
    return {
        "series": portfolios["series"], "start_date": global_start,
        "starting_capital": capital, "locked_at_utc": holdings["lock_time_utc"],
        "updated_at_utc": now_iso, "countries": out,
    }


def main():
    with open(PORTFOLIOS, encoding="utf-8") as f:
        portfolios = json.load(f)

    print("Fetching live prices, history + FX...")
    quotes, fx = gather(portfolios)
    print(f"  {len(quotes)} tickers, FX: {[(k, round(v['rate'],3)) for k,v in fx.items()]}")

    existing, lock_time = {}, None
    if os.path.exists(HOLDINGS):
        with open(HOLDINGS, encoding="utf-8") as f:
            prev = json.load(f)
        existing = prev.get("positions", {})
        lock_time = prev.get("lock_time_utc")

    positions, newly = lock_positions(portfolios, quotes, fx, existing)
    if newly or not os.path.exists(HOLDINGS):
        holdings = {
            "locked": True,
            "lock_time_utc": lock_time or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "starting_capital": portfolios["starting_capital"],
            "positions": positions,
        }
        with open(HOLDINGS, "w", encoding="utf-8") as f:
            json.dump(holdings, f, indent=2, ensure_ascii=False)
        print(f"Locked {len(newly)} new position(s): {newly}" if newly else "Locked all positions")
    else:
        holdings = {"lock_time_utc": lock_time, "positions": positions}
        print(f"Using existing lock from {lock_time}")

    data = build_data(portfolios, holdings, quotes, fx)
    with open(DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("\n=== LEADERBOARD ===")
    for i, c in enumerate(data["countries"], 1):
        print(f"{i}. {c['name']:13} ${c['value_usd']:>11,.2f}  {c['return_pct']:+.2f}%  "
              f"({len(c['history'])} history pts)")
    print(f"\nWrote {DATA_OUT}")


if __name__ == "__main__":
    main()
