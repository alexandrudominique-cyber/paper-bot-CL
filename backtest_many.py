#!/usr/bin/env python3
"""Broad Larsson backtest across ~100 coins. Runs on GitHub Actions. No keys/money."""
import json, time, datetime
import urllib.request

FEE = 0.0015
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

def fetch(sym, pages=2):
    base="https://data-api.binance.vision/api/v3/klines"
    allrows=[]; end=None
    for _ in range(pages):
        url=f"{base}?symbol={sym}USDT&interval=1d&limit=1000"
        if end: url+=f"&endTime={end}"
        try:
            with urllib.request.urlopen(url,timeout=30) as r: data=json.load(r)
        except Exception: break
        if not data: break
        allrows = data + allrows
        end = data[0][0]-1
        if len(data)<1000: break
        time.sleep(0.15)
    seen=set(); rows=[]
    for k in sorted(allrows, key=lambda x:x[0]):
        if k[0] in seen: continue
        seen.add(k[0]); rows.append(k)
    return ([float(x[2]) for x in rows],[float(x[3]) for x in rows],[float(x[4]) for x in rows])

def main():
    res=[]
    for i,c in enumerate(COINS):
        h,l,cl=fetch(c)
        if len(cl)<250: continue
        eq,hold,mdd,tr=backtest_coin(h,l,cl)
        res.append((c,eq,hold,mdd,tr,len(cl)))
        print(f"{i+1} {c}: {eq:.2f}x vs {hold:.2f}x")
    n=len(res)
    if n==0:
        open("BACKTEST_RESULTS.md","w").write("No data fetched."); return
    beat=sum(1 for r in res if r[1]>r[2]); blew=sum(1 for r in res if r[3]<-0.80)
    med=lambda xs: sorted(xs)[len(xs)//2]
    ms=med([r[1] for r in res]); mh=med([r[2] for r in res]); mdd=med([r[3] for r in res])
    ps=sum(r[1] for r in res)/n; ph=sum(r[2] for r in res)/n
    res.sort(key=lambda r:r[1], reverse=True)
    today=datetime.datetime.utcnow().strftime("%Y-%m-%d")
    L=[f"# Larsson broad backtest - {n} coins - {today}","",
       f"Fees {FEE*100:.2f}%/trade. Survivorship-biased (today's coins).","",
       "## Headline",
       f"- Beat buy and hold: **{beat}/{n}** ({beat*100//n}%)",
       f"- Still blew up (>80% drop): **{blew}/{n}**",
       f"- Median coin: strategy **{ms:.2f}x** vs hold **{mh:.2f}x** (median worst drop {mdd*100:.0f}%)",
       f"- Trade-everything equal basket: strategy **{ps:.2f}x** vs hold **{ph:.2f}x**","",
       "| Coin | Strategy | Hold | MaxDD | Trades |","|---|---|---|---|---|"]
    for c,eq,hold,dd,tr,_ in res:
        L.append(f"| {c} | {eq:.2f}x | {hold:.2f}x | {dd*100:.0f}% | {tr} |")
    open("BACKTEST_RESULTS.md","w").write("\n".join(L))

if __name__=="__main__":
    main()
