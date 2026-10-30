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
dividend_data = json.loads((OUT / 'dividend-check.json').read_text())
assert D(dividend_data['price_cny']) == price
paid_dividend = sum(D(row['per_share_cny']) for row in dividend_data['payouts'])
dividend_source = ' ; '.join(row['primary_url'] for row in dividend_data['payouts'])
model_dividend = eps * D('.75')

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
    ('假设股息率', '3.54%', model_dividend / price * 100, 2, policy + ' ; ' + q3, '未来按75%分红是测算假设，不是已宣告股息'),
    ('过去12个月实际派息股息率', '3.73%', paid_dividend / price * 100, 2, dividend_source, '含税已实施派息，与同日行情TTM口径核对'),
    ('全年持平所需Q4归母利润同比', '0.9%', pct(f['25FY']['profit'] - f['26M9']['profit'], f['25Q4']['profit']), 1, fy + ' ; ' + q3, '算术门槛，不是预测'),
]

article = REPORT.read_text()
body, references = article.split('**参考资料**', 1)
assert not re.search(r'https?://|\]\(', body), 'Sources must remain at the end'
results = []
for idx, (label, literal, value, places, source, note) in enumerate(claims, 1):
    lines = [(n, line) for n, line in enumerate(article.splitlines(), 1) if literal in line and not line.startswith('|')]
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

# Verify every numeric table cell, including the sign of each change.
main26 = b['26M9']['moutai'] + b['26M9']['series']
main25 = b['25M9']['moutai'] + b['25M9']['series']
tables = [
    ('三季度单季', {
        '营业收入': (f['26Q3']['revenue'] / E, pct(f['26Q3']['revenue'], f['25Q3']['revenue'])),
        '归母净利润': (f['26Q3']['profit'] / E, pct(f['26Q3']['profit'], f['25Q3']['profit'])),
        '扣非归母净利润': (f['26Q3']['core'] / E, pct(f['26Q3']['core'], f['25Q3']['core'])),
        '毛利率': (gross26, gross26 - gross25),
    }, q3 + ' ; ' + h1),
    ('前三季度收入', {
        '公司主营收入合计': (main26, main26 - main25),
        '直销': (b['26M9']['direct'], b['26M9']['direct'] - b['25M9']['direct']),
        '其中：i茅台': (b['26M9']['i'], b['26M9']['i'] - b['25M9']['i']),
        '批发代理': (b['26M9']['wholesale'], b['26M9']['wholesale'] - b['25M9']['wholesale']),
    }, biz + ' ; ' + oldbiz),
    ('前三季度金额', {
        '合并经营现金流': (f['26M9']['cfo'] / E, pct(f['26M9']['cfo'], f['25M9']['cfo'])),
        '销售商品、提供劳务收现': (f['26M9']['receipts'] / E, pct(f['26M9']['receipts'], f['25M9']['receipts'])),
        '归母净利润': (f['26M9']['profit'] / E, pct(f['26M9']['profit'], f['25M9']['profit'])),
    }, q3),
    ('每股股息', {
        '过去12个月实际派发': (paid_dividend, paid_dividend / price * 100),
        '盈利不变、按75%派息测算': (model_dividend, model_dividend / price * 100),
    }, dividend_source + ' ; ' + q3 + ' ; ' + policy),
]
seen = set()
active = None
for lineno, line in enumerate(article.splitlines(), 1):
    if not line.startswith('|'):
        active = None
        continue
    cells = [cell.strip() for cell in line.strip('|').split('|')]
    for table_id, (header, expected, source) in enumerate(tables):
        if len(cells) == 3 and cells[1] == header:
            active = table_id
            headers = cells
            break
    if active is None:
        continue
    header, expected, source = tables[active]
    if cells[0] not in expected:
        continue
    assert (active, cells[0]) not in seen
    seen.add((active, cells[0]))
    for column, exact in enumerate(expected[cells[0]], 1):
        match = re.fullmatch(r'([+-]?\d+\.\d{2})(%|个百分点|元)?', cells[column])
        assert match, cells[column]
        number = D(match.group(1))
        rounded = exact.quantize(D('.01'), rounding=ROUND_HALF_UP)
        assert number == rounded, (cells[0], headers[column], number, exact)
        if active == 3:
            expected_unit = '元' if column == 1 else '%'
        else:
            expected_unit = '亿元' if active == 1 or (column == 1 and cells[0] != '毛利率') else ('个百分点' if cells[0] == '毛利率' and column == 2 else '%')
        assert (match.group(2) or '亿元') == expected_unit
        results.append({
            'id': len(results) + 1,
            'label': '{} · {} · {}'.format(header, cells[0], headers[column]),
            'reported_value': float(number), 'unit': expected_unit,
            'line_number': lineno, 'raw_text': line, 'fetched_value': float(rounded),
            'exact_calculated_value': str(exact), 'fetched_source': source,
            'verification_type': 'existing_source_ledger_recalculation',
            'qualification': '表格逐格复核；区分元与亿元、百分比与百分点；实际派息与假设派息分列',
        })
assert len(seen) == 13 and len(results) == 45

sample = report_audit.sample_points(report_audit.extract_data_points(article), seed=42)
reference_line = article.splitlines().index('**参考资料**') + 1
for point in sample:
    # Reference dates are not financial metrics; actual dividend amounts in
    # references are separately checked against the declaration ledger below.
    if point['line_number'] > reference_line:
        continue
    assert any(point['line_number'] == result['line_number'] and point['reported_value'] == result['reported_value'] for result in results), point
for row in dividend_data['payouts']:
    assert row['per_share_cny'] + '元' in references
    assert D(row['per_share_cny']) == D(row['secondary_per_share_cny'])
assert paid_dividend.quantize(D('.01')) == D(dividend_data['quote_cross_check']['dividend_per_share_ttm_cny'])
assert (paid_dividend / price * 100).quantize(D('.01')) == D(dividend_data['quote_cross_check']['dividend_yield_ttm_percent'])

capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    print('Historical trailing dividend yield:')
    financial_rigor.verify_valuation(price, eps=eps, dividend=paid_dividend)
    financial_rigor.cross_validate('TTM dividend yield', {'paid cash dividends / closing price': paid_dividend / price * 100, 'Futu TTM': D(dividend_data['quote_cross_check']['dividend_yield_ttm_percent'])}, unit='%', tolerance_pct=1)
    print('Hypothetical yield at 75% payout:')
    financial_rigor.verify_valuation(price, eps=eps, dividend=model_dividend)
    verdict = report_audit.render_verdict(results, report_name=str(REPORT.relative_to(ROOT)))
clean = re.sub(r'\x1b\[[0-9;]*m', '', capture.getvalue())
clean = '\n'.join(line.rstrip() for line in clean.splitlines()) + '\n'
(OUT / 'audit-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
(OUT / 'audit-verdict.txt').write_text(clean)
extract = subprocess.run([sys.executable, str(ROOT / 'tools/report_audit.py'), 'extract', '--report', str(REPORT.relative_to(ROOT)), '--seed', '42'], cwd=str(ROOT), text=True, stdout=subprocess.PIPE, check=True)
(OUT / 'audit-extract.txt').write_text('\n'.join(line.rstrip() for line in extract.stdout.splitlines()) + '\n')
assert verdict['verdict'] == 'PASS' and verdict['total'] == len(results)
print('PASS: {} prose claims and {} table cells match source-ledger arithmetic and displayed rounding.'.format(len(claims), len(results) - len(claims)))
print('All source links are in the final reference list.')
