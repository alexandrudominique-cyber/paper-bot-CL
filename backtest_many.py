#!/usr/bin/env python3
"""Cross-asset Larsson bot (crypto+stocks+gold+bonds) + bot-vs-DCA."""
import json, time, datetime, csv, io, traceback
import urllib.request
from collections import defaultdict

FEE=0.0015
CRYPTO="BTC ETH SOL LTC".split()
STOCKS="SPY QQQ GLD TLT".split()   # S&P500, Nasdaq100, Gold, 20y Treasuries

def smma(v,n):
    o=[None]*len(v)
    if len(v)<n: return o
    o[n-1]=sum(v[:n])/n
    for i in range(n,len(v)): o[i]=(o[i-1]*(n-1)+v[i])/n
    return o
def regime(high,low):
    s=[(h+l)/2 for h,l in zip(high,low)]
    v1,m1,m2,v2=smma(s,15),smma(s,19),smma(s,25),smma(s,29)
    r=[];cur=0
    for i in range(len(s)):
        if None in (v1[i],m1[i],m2[i],v2[i]): r.append(0);continue
        a,b,c=v1[i]<m1[i],v1[i]<v2[i],m2[i]<v2[i]
        st=0 if ((a!=b)or(c!=b)) else (-1 if v1[i]<v2[i] else 1)
        if st==1:cur=1
        elif st==-1:cur=0
        r.append(cur)
    return r

def fetch_crypto(sym,pages=3):
    base="https://data-api.binance.vision/api/v3/klines";allr=[];end=None
    for _ in range(pages):
        u=f"{base}?symbol={sym}USDT&interval=1d&limit=1000"
        if end:u+=f"&endTime={end}"
        try:
            with urllib.request.urlopen(u,timeout=30) as r:d=json.load(r)
        except Exception:break
        if not isinstance(d,list) or not d:break
        allr=d+allr;end=d[0][0]-1
        if len(d)<1000:break
        time.sleep(0.15)
    seen=set();rows=[]
    for k in sorted(allr,key=lambda x:x[0]):
        if k[0] in seen:continue
        seen.add(k[0]);rows.append(k)
    dt=[datetime.datetime.utcfromtimestamp(x[0]//1000).strftime('%Y-%m-%d') for x in rows]
    return dt,[float(x[2]) for x in rows],[float(x[3]) for x in rows],[float(x[4]) for x in rows]

def fetch_stooq(sym):
    u=f"https://stooq.com/q/d/l/?s={sym.lower()}.us&i=d"
    try:
        with urllib.request.urlopen(u,timeout=30) as r: txt=r.read().decode()
    except Exception: return [],[],[],[]
    dt=[];h=[];l=[];c=[]
    for row in csv.DictReader(io.StringIO(txt)):
        try: dt.append(row["Date"]);h.append(float(row["High"]));l.append(float(row["Low"]));c.append(float(row["Close"]))
        except Exception: continue
    return dt,h,l,c

def sim_bot(retd,sigd,assets,days):
    dates=sorted(retd)[-days:] if days else sorted(retd)
    N=len(assets); eq=10000.0;peak=eq;mdd=0.0;prev={}
    for d in dates:
        w={a:(1.0/N) for a in assets if sigd[d].get(a)==1 and a in retd[d]}
        pr=sum(w[a]*retd[d].get(a,0.0) for a in w)
        allc=set(w)|set(prev);to=sum(abs(w.get(a,0)-prev.get(a,0)) for a in allc)
        eq*=(1+pr-to*FEE);peak=max(peak,eq);mdd=min(mdd,eq/peak-1);prev=w
    return eq,mdd

def hold_basket(cl_by,assets,dates):
    N=len(assets); val=0.0
    for a in assets:
        ser=[cl_by[a][d] for d in dates if d in cl_by[a]]
        if len(ser)>=2: val+=(10000.0/N)*(ser[-1]/ser[0])
    return val

def dca_basket(cl_by,assets,dates):
    buys=dates[::7]
    if not buys: return 0.0
    per=10000.0/len(buys); units=defaultdict(float)
    for d in buys:
        avail=[a for a in assets if d in cl_by[a]]
        if not avail: continue
        for a in avail: units[a]+=(per/len(avail))/cl_by[a][d]
    val=0.0
    for a in assets:
        last=[cl_by[a][d] for d in dates if d in cl_by[a]]
        if last: val+=units[a]*last[-1]
    return val

def main():
    try:
        retd=defaultdict(dict);sigd=defaultdict(dict);cl_by={};assets=[]
        def add(a,dt,h,l,c):
            if len(c)<250: return
            reg=regime(h,l); cl_by[a]={}
            for i in range(len(c)): cl_by[a][dt[i]]=c[i]
            for i in range(1,len(c)):
                retd[dt[i]][a]=c[i]/c[i-1]-1; sigd[dt[i]][a]=reg[i-1]
            assets.append(a)
        for a in CRYPTO: add(a,*fetch_crypto(a))
        for a in STOCKS: add(a,*fetch_stooq(a))
        if not assets:
            open("BACKTEST_RESULTS.md","w").write("No data loaded."); return
        def block(days,label):
            dates=sorted(retd)[-days:] if days else sorted(retd)
            b,bdd=sim_bot(retd,sigd,assets,days)
            h=hold_basket(cl_by,assets,dates); d=dca_basket(cl_by,assets,dates)
            return (f"### {label}\n"
                    f"- Bot (Larsson, diversified): ${b:,.0f} ({b/10000:.2f}x), worst drop {bdd*100:.0f}%\n"
                    f"- Buy&hold basket:            ${h:,.0f} ({h/10000:.2f}x)\n"
                    f"- DCA basket (weekly):        ${d:,.0f} ({d/10000:.2f}x)\n")
        today=datetime.datetime.utcnow().strftime("%Y-%m-%d")
        L=[f"# Cross-asset bot vs Hold vs DCA - {today}","",
           f"Assets loaded ({len(assets)}): {', '.join(assets)}",
           "$10,000 start. Equal sleeves, fees 0.15%/trade.","",
           block(1095,"Last ~3 years"), block(0,"Full window")]
        open("BACKTEST_RESULTS.md","w").write("\n".join(L))
    except Exception:
        open("BACKTEST_RESULTS.md","w").write("# ERROR\n\n```\n"+traceback.format_exc()+"\n```")

if __name__=="__main__":
    main()
