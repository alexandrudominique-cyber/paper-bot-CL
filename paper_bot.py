#!/usr/bin/env python3
"""Larsson paper-trading bot (crypto). Runs daily, virtual $10,000, no real money."""
import os, json, csv, datetime
import urllib.request

UNIVERSE     = {"BTC": "XBTUSD", "ETH": "ETHUSD", "LTC": "LTCUSD", "XRP": "XRPUSD"}
START_EQUITY = 10_000.0
PER_POSITION = 0.25      # up to 25% of the account per coin
FEE          = 0.0015    # 0.15% per trade
TRADE_THRESH = 0.01      # only rebalance if change > 1% of account

STATE_FILE  = "portfolio_state.json"
LOG_FILE    = "trades_log.csv"
STATUS_FILE = "STATUS.md"

def smma(vals, length):
    out = [None] * len(vals)
    if len(vals) < length:
        return out
    out[length - 1] = sum(vals[:length]) / length
    for i in range(length, len(vals)):
        out[i] = (out[i - 1] * (length - 1) + vals[i]) / length
    return out

def larsson_states(high, low):
    src = [(h + l) / 2 for h, l in zip(high, low)]
    v1, m1, m2, v2 = smma(src,15), smma(src,19), smma(src,25), smma(src,29)
    st = []
    for i in range(len(src)):
        if None in (v1[i], m1[i], m2[i], v2[i]):
            st.append(0); continue
        a, b, c = v1[i] < m1[i], v1[i] < v2[i], m2[i] < v2[i]
        if (a != b) or (c != b):      st.append(0)
        elif v1[i] < v2[i]:           st.append(-1)
        else:                         st.append(1)
    return st

def current_regime(states):
    reg = 0
    for s in states:
        if s == 1:   reg = 1
        elif s == -1: reg = 0
    return reg

def fetch_kraken_daily(pair):
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=1440"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    res = data["result"]
    key = [k for k in res if k != "last"][0]
    rows = res[key][:-1]
    high  = [float(x[2]) for x in rows]
    low   = [float(x[3]) for x in rows]
    close = [float(x[4]) for x in rows]
    return high, low, close

def get_prices_and_signals():
    signals, price = {}, {}
    for name, pair in UNIVERSE.items():
        high, low, close = fetch_kraken_daily(pair)
        signals[name] = current_regime(larsson_states(high, low))
        price[name] = close[-1]
    return signals, price

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"cash": START_EQUITY, "units": {c: 0.0 for c in UNIVERSE}, "runs": 0}

def main():
    signals, price = get_prices_and_signals()
    s = load_state()
    cash = s["cash"]; units = {c: float(s["units"].get(c, 0.0)) for c in UNIVERSE}
    equity = cash + sum(units[c] * price[c] for c in UNIVERSE)

    trades = []
    for c in UNIVERSE:
        target = equity * (PER_POSITION if signals[c] else 0.0)
        current = units[c] * price[c]
        diff = target - current
        if abs(diff) > equity * TRADE_THRESH:
            fee = abs(diff) * FEE
            cash -= diff + fee
            units[c] += diff / price[c]
            trades.append((c, "BUY" if diff > 0 else "SELL", round(abs(diff), 2), round(price[c], 4)))

    equity = cash + sum(units[c] * price[c] for c in UNIVERSE)
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    json.dump({"cash": cash, "units": units, "runs": s["runs"] + 1, "last": today,
               "equity": round(equity, 2)}, open(STATE_FILE, "w"), indent=2)

    new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["date", "coin", "side", "usd", "price"])
        for t in trades: w.writerow([today, *t])

    lines = [f"# Paper bot status - {today}", "",
             f"**Account value: ${equity:,.2f}**  (started at ${START_EQUITY:,.0f})",
             f"Cash: ${cash:,.2f}  |  Run #{s['runs']+1}", "", "| Coin | Signal | Position |", "|---|---|---|"]
    for c in UNIVERSE:
        sig = "GOLD (in)" if signals[c] else "BLUE / out (cash)"
        lines.append(f"| {c} | {sig} | ${units[c]*price[c]:,.2f} |")
    lines += (["", "### Trades this run"] + [f"- {t[1]} {t[0]} ~${t[2]:,.0f} @ ${t[3]:,}" for t in trades]) if trades else ["", "_No trades this run._"]
    open(STATUS_FILE, "w").write("\n".join(lines))
    print("\n".join(lines))

if __name__ == "__main__":
    main()
