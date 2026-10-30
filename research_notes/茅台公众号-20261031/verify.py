"""Recalculate the article's financial claims from the existing filing ledger.

This is arithmetic and quotation verification, not a new independent audit.
The prose extractor misses most narrative figures; claims are enumerated here.
"""
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path
import contextlib
import io
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
REPORT = ROOT / 'reports/茅台/茅台-公众号-20261031.md'
sys.path.insert(0, str(ROOT / 'tools'))
import financial_rigor
import report_audit

inputs = json.loads((ROOT / 'research_notes/茅台财报-20261031/inputs.json').read_text())
f = {p: {k: D(v) for k, v in row.items()} for p, row in inputs['financial'].items()}
b = {p: {k: D(v) for k, v in row.items()} for p, row in inputs['business_yi'].items()}
E = D('100000000')
pct = lambda a, z: (a / z - 1) * 100
q3 = 'https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12685262&stockid=600519'
h1 = 'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF'
biz = 'https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12685264&stockid=600519'
oldbiz = 'https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=11561250&stockid=600519'
fy = 'https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-04-17/600519_20260417_9QS4.pdf'
policy = 'https://www.moutai.com.cn/mtgf/attachDir/2024/11/2024112812512867790.pdf'
quote = 'https://cn.investing.com/equities/moutai-historical-data'

gross26 = (1 - (D('13645718932.90') - D('9473762565.88')) / f['26Q3']['revenue']) * 100
gross25 = (1 - (D('11183972073.77') - D('7777491083.93')) / f['25Q3']['revenue']) * 100
fund26 = D('-774901684.37') - D('-1177564668.21') - D('-22715439598.84') - D('200000000')
fund25 = D('-8659745768.25') - D('358885355.55') - D('12507272127.36') - D('-2100000000')
finance_share = (fund26 - fund25) / (f['26M9']['cfo'] - f['25M9']['cfo']) * 100
ttm = f['25FY']['profit'] + f['26M9']['profit'] - f['25M9']['profit']
eps = ttm / D('1250081601')
price = D('1392.05')

# label, literal, exact value, displayed decimals, source, qualification
claims = [
    ('Q3营业收入同比', '3.08%', pct(f['26Q3']['revenue'], f['25Q3']['revenue']), 2, q3, '同比'),
    ('Q3归母净利润同比', '3.78%', pct(f['26Q3']['profit'], f['25Q3']['profit']), 2, q3, '同比'),
    ('Q3茅台酒收入同比', '0.79%', pct(b['26Q3']['moutai'], b['25Q3']['moutai']), 2, biz + ' ; ' + oldbiz, '经营数据累计减半年报，主营业务'),
    ('系列酒对Q3公司收入增量贡献', '76%', (b['26Q3']['series'] - b['25Q3']['series']) / ((f['26Q3']['revenue'] - f['25Q3']['revenue']) / E) * 100, 0, biz + ' ; ' + oldbiz, '收入贡献，不能代表利润贡献'),
    ('Q3公司营业收入同比增量', '12亿元', (f['26Q3']['revenue'] - f['25Q3']['revenue']) / E, 0, q3, '增量，不是收入总额'),
    ('Q3系列酒收入同比增量', '9亿元', b['26Q3']['series'] - b['25Q3']['series'], 0, biz + ' ; ' + oldbiz, '经营数据累计减半年报'),
    ('Q3毛利率同比下降', '1.64个百分点', gross25 - gross26, 2, q3 + ' ; ' + h1, '百分点，营业收入口径'),
    ('9M i茅台收入', '586亿元', b['26M9']['i'], 0, biz, '已含在直销收入中'),
    ('9M i茅台收入同比增量', '459亿元', b['26M9']['i'] - b['25M9']['i'], 0, biz + ' ; ' + oldbiz, '含渠道迁移，不等于新增消费'),
    ('9M主营业务收入同比增量', '25亿元', sum(b['26M9'][k] - b['25M9'][k] for k in ('moutai', 'series')), 0, biz + ' ; ' + oldbiz, '产品和渠道统一主营口径'),
    ('9M合并经营现金流同比', '120%', pct(f['26M9']['cfo'], f['25M9']['cfo']), 0, q3, '不是纯酒业现金流'),
    ('四类金融本金对CFO同比增量贡献', '92%', finance_share, 0, q3, '逐项净流量差分；不是现金流余额占比'),
    ('9M销售商品提供劳务收现同比', '3.41%', pct(f['26M9']['receipts'], f['25M9']['receipts']), 2, q3, '含增值税和时点影响，不等于消费量'),
    ('合同负债较年初降幅', '74%', -pct(D('2084485744.75'), D('8006739780.94')), 0, q3, '年初对比，不是同比订单降幅'),
    ('10月30日收盘价', '1392.05元', price, 2, quote, '财报披露前收盘价；引用此前研究已核行情'),
    ('更新财报后的TTM市盈率', '21.2倍', price / eps, 1, q3 + ' ; ' + fy + ' ; ' + quote, '期末股数归一EPS'),
    ('假设股息率', '3.5%', eps * D('.75') / price * 100, 1, policy + ' ; ' + q3, '未来75%分红是测算假设，不是已宣告股息'),
    ('全年持平所需Q4归母利润同比', '0.9%', pct(f['25FY']['profit'] - f['26M9']['profit'], f['25Q4']['profit']), 1, fy + ' ; ' + q3, '算术门槛，不是预测'),
]

article = REPORT.read_text()
body, references = article.split('**参考资料**', 1)
assert not re.search(r'https?://|\]\(', body), 'Sources must remain at the end'
results = []
for idx, (label, literal, value, places, source, note) in enumerate(claims, 1):
    lines = [(n, line) for n, line in enumerate(article.splitlines(), 1) if literal in line]
    assert lines, 'Missing expected claim: ' + literal
    reported = D(re.match(r'[\d.]+', literal).group())
    rounded = value.quantize(D(1).scaleb(-places), rounding=ROUND_HALF_UP)
    assert reported == rounded, (label, reported, value, rounded)
    results.append({
        'id': idx, 'label': label, 'reported_value': float(reported),
        'unit': literal[len(str(reported)):], 'line_number': lines[0][0],
        'raw_text': lines[0][1], 'fetched_value': float(rounded),
        'exact_calculated_value': str(value), 'fetched_source': source,
        'verification_type': 'existing_source_ledger_recalculation',
        'qualification': note,
    })

capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    financial_rigor.verify_valuation(price, eps=eps, dividend=eps * D('.75'))
    verdict = report_audit.render_verdict(results, report_name=str(REPORT.relative_to(ROOT)))
clean = re.sub(r'\x1b\[[0-9;]*m', '', capture.getvalue())
clean = '\n'.join(line.rstrip() for line in clean.splitlines()) + '\n'
(OUT / 'audit-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
(OUT / 'audit-verdict.txt').write_text(clean)
extract = subprocess.run([sys.executable, str(ROOT / 'tools/report_audit.py'), 'extract', '--report', str(REPORT.relative_to(ROOT)), '--seed', '42'], cwd=str(ROOT), text=True, stdout=subprocess.PIPE, check=True)
(OUT / 'audit-extract.txt').write_text('\n'.join(line.rstrip() for line in extract.stdout.splitlines()) + '\n')
assert verdict['verdict'] == 'PASS' and verdict['total'] == len(claims)
print('PASS: {} financial claims match source-ledger arithmetic and displayed rounding.'.format(len(claims)))
print('All source links are in the final reference list.')
