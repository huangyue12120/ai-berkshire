# 贵州茅台2026Q3报告核验记录

研究日期：2026-10-31（北京时间）。对应报告：`reports/茅台/贵州茅台-earnings-2026Q3-20261031.md`。

`calculate.py` 使用 Decimal 计算单季、同比、现金流调整、估值与情景，并调用仓库 `tools/financial_rigor.py` 做交叉核验及市值、估值验证。运行 `python3 research_notes/茅台财报-20261031/calculate.py` 可重建 `inputs.json`、`calculations.txt`、`financial_rigor.log`。`supplement-calculations.txt` 保存营业利润与周转指标补充运算，基于下列原始披露。

最终报告抽检提取91项、固定种子42抽样14项：10项实际披露或派生指标数值核对通过，3项预测情景仅验证算术，1项会计准则编号从财务抽检排除。分类见 `audit-classified.json`，事实判决见 `audit-verdict.txt`。单一原始来源与派生计算均明确标识，不宣称所有细项已获独立双源确认。

主要来源：

- [2026Q3完整财报](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12685262&stockid=600519)，PDF第1—3页摘要及经营数据，第5—8页资产负债表，第8—10页利润表，第10—12页现金流量表。
- [2026H1原始财报](https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF)。
- [2026Q1原始财报](https://static.cninfo.com.cn/finalpage/2026-04-25/1225187851.PDF)。
- [2025Q3原始财报](https://static.cninfo.com.cn/finalpage/2025-10-30/1224764517.PDF)。
- [2025全年原始财报](https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-04-17/600519_20260417_9QS4.pdf)。
- [2025H1原文](https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=11296249&stockid=600519)。
- [官方管理层说明会](https://www.moutai.com.cn/mtjt/2026-08/21/article_2026082123470131571.html)。

交叉核验：收入及归母利润使用[每日经济新闻](https://www.nbd.com.cn/articles/2026-10-30/4631527.html)，扣非及部分经营数据使用[证券之星](https://finance.stockstar.com/IG2026103000054670.shtml)，渠道使用[财联社](https://api3.cls.cn/share/article/2520944?app=&os=CailianpressWeb&sv=864)，毛利率使用[数据库报道](https://www.hstong.com/news/detail/26103020333539148)，现金流使用[中国基金报](https://www.chnfund.com/article/ARfa686a88-a599-9653-cbdf-3a249ee2323d)，价格使用[Investing历史行情](https://cn.investing.com/equities/moutai-historical-data)。媒体底层引用仍为公司披露，核验不是独立审计。

补充指标：周转天数均为期初、期末余额平均值/九个月收入或营业成本×273。2026年应收账款期初2609048.49元、期末364538360.24元；2025年同期18974192.75元、25531737.62元。2026年存货期初61427421796.18元、期末61390820964.46元；2025年同期54343285157.47元、55858862716.48元。各期收入与成本见原报与计算脚本。该简化周转口径不可替代账龄、基酒或渠道库存分析。

原始PDF及网页转录保留在本地；本次提交仅包括研究报告和自主生成的数字、计算及核验记录。
