from decimal import Decimal as D, getcontext
from pathlib import Path
import sys, json, io, contextlib
getcontext().prec = 28
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import financial_rigor as rigor
OUT = Path(__file__).parent
E = D('100000000')
def v(s): return [D(x) for x in s.split()]
keys = ['revenue','profit','core','cfo','capex','receipts']
raw = {
'25Q1': '50600957885.78 26847474238.76 26849883702.90 8809195646.38 901104348.81 56144062118.93',
'25H1': '89389354416.84 45402962298.10 45390247623.82 13119061031.33 1595995809.23 95086614960.23',
'25M9': '128453707655.86 64626746712.18 64680616431.20 38196802155.27 2282862269.89 138791719991.59',
'25FY': '168838102514.79 82320067101.68 82293107655.25 61522204989.35 3127594916.41 183990403487.80',
'26Q1': '53909252220.51 27242512886.45 27239985194.41 26909891269.13 604791583.89 56392589148.92',
'26H1': '90703260964.48 44516880421.86 44464207646.01 70690750119.06 832142752.28 98421697395.39',
'26M9': '130970743649.04 64467425981.95 64324824599.18 84058979832.29 1449998414.96 143522752519.23',
}
data = {p: dict(zip(keys,v(s))) for p,s in raw.items()}
for yr in ['25','26']:
    for q,a,b in [('Q2','H1','Q1'),('Q3','M9','H1')]:
        data[yr+q] = {k:data[yr+a][k]-data[yr+b][k] for k in keys}
data['25Q4']={k:data['25FY'][k]-data['25M9'][k] for k in keys}
def pct(a,b): return (a/b-1)*100
lines=[]
def emit(label,val): lines.append(f'{label}: {val}')
for p in ['25Q3','25Q4','26Q1','26Q2','26Q3']:
    emit(p,{k:str(x/E) for k,x in data[p].items()})
    if p.startswith('26'):
        emit(p+' yoy',{k:str(pct(x,data['25'+p[2:]][k])) for k,x in data[p].items()})
prodkeys=['moutai','series','direct','wholesale','domestic','overseas','i']
products={
'25H1':'7558994.89 1376252.94 4000959.89 4934287.94 8645947.06 289300.77 1076043.75',
'25M9':'11051350.26 1788435.48 5555539.39 7284246.35 12450477.45 389308.29 1269174.00',
'26Q1':'4600486.86 788087.83 2950403.39 2438171.30 5373378.73 15195.96 2155304.59',
'26H1':'7772443.79 1293418.65 5196204.70 3869657.74 8962212.26 103650.18 4026356.42',
'26M9':'11292545.23 1796854.27 7377359.30 5712040.20 12925258.61 164140.89 5856230.60',
}
prod={p:dict(zip(prodkeys,[x/D('10000') for x in v(s)])) for p,s in products.items()}
for yr in ['25','26']: prod[yr+'Q3']={k:prod[yr+'M9'][k]-prod[yr+'H1'][k] for k in prodkeys}
prod['26Q2']={k:prod['26H1'][k]-prod['26Q1'][k] for k in prodkeys}
for p in ['26M9','25Q3','26Q1','26Q2','26Q3']:
    emit('business '+p,prod[p])
    if p in ['26M9','26Q3']:emit('business yoy '+p,{k:pct(x,prod['25'+p[2:]][k]) for k,x in prod[p].items()})
emit('series share of Q3 revenue growth',(prod['26Q3']['series']-prod['25Q3']['series'])/((data['26Q3']['revenue']-data['25Q3']['revenue'])/E)*100)
for p in ['25M9','26M9','26Q1','26Q2','26Q3']:
    total=prod[p]['moutai']+prod[p]['series']
    emit(p+' direct share',prod[p]['direct']/total*100)
    emit(p+' i share',prod[p]['i']/total*100)
emit('Q3 i sequential',pct(prod['26Q3']['i'],prod['26Q2']['i']))
cost={'26M9':D('13645718932.90'),'25M9':D('11183972073.77'),'26H1':D('9473762565.88'),'25H1':D('7777491083.93')}
for yr in ['25','26']:cost[yr+'Q3']=cost[yr+'M9']-cost[yr+'H1']
for p in ['25M9','26M9','25Q3','26Q3']:
    emit(p+' gross margin',(1-cost[p]/data[p]['revenue'])*100)
    emit(p+' parent margin',data[p]['profit']/data[p]['revenue']*100)
emit('M9 revenue increase',(data['26M9']['revenue']-data['25M9']['revenue'])/E)
emit('M9 cost increase',(cost['26M9']-cost['25M9'])/E)
emit('M9 gross profit increase',(data['26M9']['revenue']-cost['26M9']-data['25M9']['revenue']+cost['25M9'])/E)
tax26=D('20776015728.76')-D('14682159453.47');tax25=D('20645707926.55')-D('13942384581.48')
sale26=D('4830628836.78')-D('3206308341.53');sale25=D('4478672252.48')-D('3260462949.46')
emit('Q3 tax decline',(tax26-tax25)/E)
emit('Q3 sales expense yoy',pct(sale26,sale25))
emit('Q3 gross profit increase',(data['26Q3']['revenue']-cost['26Q3']-data['25Q3']['revenue']+cost['25Q3'])/E)
emit('Q3 pretax increase',(D('27579242794.34')-(D('89403444454.68')-D('62778000766.82')))/E)
fund26=v('-774901684.37 -1177564668.21 -22715439598.84 200000000')
fund25=v('-8659745768.25 358885355.55 12507272127.36 -2100000000')
fund_effect=lambda x:x[0]-x[1]-x[2]-x[3]
adj26=data['26M9']['cfo']-fund_effect(fund26);adj25=data['25M9']['cfo']-fund_effect(fund25)
emit('financial principal movement effect M9',(fund_effect(fund26)-fund_effect(fund25))/E)
emit('financial principal movement explanation percent',(fund_effect(fund26)-fund_effect(fund25))/(data['26M9']['cfo']-data['25M9']['cfo'])*100)
emit('adjusted CFO observation M9',(adj26/E,adj25/E,pct(adj26,adj25)))
emit('CFO over parent NI',data['26M9']['cfo']/data['26M9']['profit']*100)
emit('CFO over consolidated NI',data['26M9']['cfo']/D('66717143218.04')*100)
emit('mechanical CFO less capex',(data['26M9']['cfo']-data['26M9']['capex'])/E)
emit('adjusted observation less capex',((adj26-data['26M9']['capex'])/E,(adj25-data['25M9']['capex'])/E))
emit('contract liability qoq',pct(D('2084485744.75'),D('3177561597.07')))
emit('cash receipts yoy',pct(data['26M9']['receipts'],data['25M9']['receipts']))
share=D('1250081601');price=D('1392.05');ttm=data['25FY']['profit']+data['26M9']['profit']-data['25M9']['profit'];eps=ttm/share
emit('ttm profit',ttm/E);emit('ttm EPS',eps);emit('PE',price/eps);emit('PB',price/(D('271204740541.63')/share))
emit('FY flat Q4 requirement',(data['25FY']['profit']-data['26M9']['profit'])/E)
emit('FY flat Q4 required yoy',pct(data['25FY']['profit']-data['26M9']['profit'],data['25Q4']['profit']))
emit('payout75 yield',eps*D('.75')/price*100)
for g,pe in [('0','16'),('.04','20'),('.07','24')]:
    growth=D(g);multiple=D(pe);future=eps*(1+growth)**5;div=sum(eps*(1+growth)**t*D('.75') for t in range(1,6));terminal=future*multiple
    annual=((terminal+div)/price)**(D(1)/D(5))-1
    emit('5Y scenario '+g,{'EPS':future,'terminal':terminal,'dividends':div,'total_return':(terminal+div)/price-1,'annualized':annual})
for p in ['1100','1200','1300','1392.05','1500']:
    emit('price sensitivity '+p,{'PE':D(p)/eps,'payout75_yield':eps*D('.75')/D(p)*100})
validation=io.StringIO()
with contextlib.redirect_stdout(validation):
    rigor.verify_market_cap(price,share,D('1740000000000'),'CNY')
    rigor.verify_valuation(price,eps=eps,bvps=D('271204740541.63')/share)
    for label,a,b in [('9M revenue',data['26M9']['revenue']/E,'1309.71'),('9M parent profit',data['26M9']['profit']/E,'644.67'),('Q3 revenue',data['26Q3']['revenue']/E,'402.67'),('Q3 profit',data['26Q3']['profit']/E,'199.51'),('9M CFO',data['26M9']['cfo']/E,'840.59'),('i revenue',prod['26M9']['i'],'585.62')]:
        rigor.cross_validate(label,{'company filing':a,'separate media check':D(b)},unit='亿元',tolerance_pct=1)
(OUT/'financial_rigor.log').write_text(validation.getvalue())
(OUT/'calculations.txt').write_text('\n'.join(lines))
(OUT/'inputs.json').write_text(json.dumps({'financial':data,'business_yi':prod},default=str,ensure_ascii=False,indent=2))
print('\n'.join(lines))
print(validation.getvalue())
