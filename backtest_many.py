#!/usr/bin/env python3
"""Broad Larsson backtest + realistic $10k portfolio. Robust version."""
import json, time, datetime, traceback
import urllib.request
from collections import defaultdict

FEE = 0.0015
CAP = 0.08
COINS = ("BTC ETH BNB SOL XRP ADA DOGE TRX AVAX LINK DOT MATIC LTC BCH NEAR UNI ATOM XLM "
         "ETC FIL HBAR APT ARB OP INJ AAVE GRT ALGO QNT EGLD SAND MANA AXS THETA XTZ EOS "
         "FLOW CHZ ZEC ENJ BAT DASH ZIL WAVES KSM CRV COMP SNX YFI SUSHI 1INCH LRC RUNE "
         "GALA ROSE ICP FTM ONE CELO KAVA ANKR OCEAN STORJ SKL BAND NMR REN OMG KNC "
         "BAL ZRX CVC DNT NKN ONT IOST QTUM ICX SC DGB RVN ZEN XVG STMX CTSI OGN "
         "MTL DENT KEY CKB HOT WIN VET IOTA NEO GAS").split()

def smma(vals, length):
    out=[None]*len(vals)
    if len(vals)<length: return out
    out[length-1]=sum(vals[:length])/length
    for i in range(length,len(vals)):
        out[i]=(out[i-1]*(length-1)+vals[i])/length
    return out

def regime_series(high, low):
    src=[(h+l)/2 for h,l in zip(high,low)]
    v1,m1,m2,v2=smma(src,15),smma(src,19),smma(src,25),smma(src,29)
    reg=[]; cur=0
    for i in range(len(src)):
        if None in (v1[i],m1[i],m2[i],v2[i]): reg.append(0); continue
        a,b,c=v1[i]<m1[i],v1[i]<v2[i],m2[i]<v2[i]
        if (a!=b) or (c!=b): st=0
        elif v1[i]<v2[i]: st=-1
        else: st=1
        if st==1: cur=1
        elif st==-1: cur=0
        reg.append(cur)
    return reg

def backtest_coin(high, low, close):
    reg=regime_series(high,low)
    eq=1.0; peak=1.0; mdd=0.0; pos=0; trades=0
    for i in range(1,len(close)):
        p=reg[i-1]
        if p!=pos: trades+=1; eq*=(1-FEE); pos=p
        eq*=(1+p*(close[i]/close[i-1]-1))
        peak=max(peak,eq); mdd=min(mdd, eq/peak-1)
    return eq, close[-1]/close[0], mdd, trades

def fetch(sym, pages=3):
    base="https://data-api.binance.vision/api/v3/klines"
    allrows=[]; end=None
    for _ in range(pages):
        url=f"{base}?symbol={sym}USDT&interval=1d&limit=1000"
        if end: url+=f"&endTime={end}"
        try:
            with urllib.request.urlopen(url,timeout=30) as r: data=json.load(r)
        except Exception: break
        if not isinstance(data, list) or not data: break
        allrows = data + allrows
        end = data[0][0]-1
        if len(data)<1000: break
        time.sleep(0.15)
    seen=set(); rows=[]
    for k in sorted(allrows, key=lambda x:x[0]):
        if k[0] in seen: continue
        seen.add(k[0]); rows.append(k)
    return ([float(x[2]) for x in rows],[float(x[3]) for x in rows],
            [float(x[4]) for x in rows],[int(x[0]) for x in rows])

def sim_portfolio(retd, sigd, days):
    dates=sorted(retd)[-days:] if days else sorted(retd)
    eq=10000.0; peak=eq; mdd=0.0; prev={}
    for d in dates:
        golds=[c for c in sigd[d] if sigd[d].get(c)==1 and c in retd[d]]
        w=min(CAP,1.0/len(golds)) if golds else 0.0
        weights={c:w for c in golds}
        pr=sum(weights[c]*retd[d].get(c,0.0) for c in weights)
        allc=set(weights)|set(prev); to=sum(abs(weights.get(c,0)-prev.get(c,0)) for c in allc)
        eq*=(1+pr-to*FEE); peak=max(peak,eq); mdd=min(mdd, eq/peak-1); prev=weights
    return eq, mdd, len(dates)

def main():
    try:
        res=[]; retd=defaultdict(dict); sigd=defaultdict(dict)
        for i,c in enumerate(COINS):
            try:
                h,l,cl,ts=fetch(c)
                if len(cl)<250: continue
                eq,hold,mdd,tr=backtest_coin(h,l,cl)
                res.append((c,eq,hold,mdd,tr))
                reg=regime_series(h,l)
                dts=[datetime.datetime.utcfromtimestamp(t//1000).strftime('%Y-%m-%d') for t in ts]
                for j in range(1,len(cl)):
                    retd[dts[j]][c]=cl[j]/cl[j-1]-1; sigd[dts[j]][c]=reg[j-1]
            except Exception as e:
                print("skip",c,e); continue
        n=len(res)
        if n==0:
            open("BACKTEST_RESULTS.md","w").write("No data fetched (network/geo?)."); return
        eq3,dd3,d3=sim_portfolio(retd,sigd,1095)
        eqA,ddA,dA=sim_portfolio(retd,sigd,0)
        beat=sum(1 for r in res if r[1]>r[2]); blew=sum(1 for r in res if r[3]<-0.80)
        res.sort(key=lambda r:r[1], reverse=True)
        today=datetime.datetime.utcnow().strftime("%Y-%m-%d")
        L=[f"# Larsson broad backtest - {n} coins - {today}","",
           "## REAL BOT: $10,000 start, max 8% per coin",
           f"- **Last 3 years (~{d3} days): ${eq3:,.0f}  ({eq3/10000:.2f}x)  worst drop {dd3*100:.0f}%**",
           f"- Full window (~{dA} days): ${eqA:,.0f}  ({eqA/10000:.2f}x)  worst drop {ddA*100:.0f}%","",
           f"## Per-coin: strategy beat hold on {beat}/{n}; {blew}/{n} still dropped >80%","",
           "| Coin | Strategy | Hold | MaxDD | Trades |","|---|---|---|---|---|"]
        for c,eq,hold,dd,tr in res:
            L.append(f"| {c} | {eq:.2f}x | {hold:.2f}x | {dd*100:.0f}% | {tr} |")
        open("BACKTEST_RESULTS.md","w").write("\n".join(L))
    except Exception:
        open("BACKTEST_RESULTS.md","w").write("# ERROR\n\n```\n"+traceback.format_exc()+"\n```")

if __name__=="__main__":
    main()
