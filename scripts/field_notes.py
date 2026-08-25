#!/usr/bin/env python3
"""What each figure actually measures, defined once.

The caveats already existed in three forms and none of them reached a reader:
prose in the README that nobody opens while looking at a map, column comments
in Unity Catalog that only a SQL user sees, and a duplicate set of those
comments in a second script. Three copies of a definition is two too many, and
the page — where the numbers are actually read — had none of them.

So they live here, bilingually, and everything imports them:

    build_map.py            bakes them into the page, for the reader and the model
    databricks_views.py     declares them on the view columns
    databricks_lineage.py   declares them on the base table columns

A note answers one question: if someone acts on this number, what do they need
to know that the number alone does not tell them? Anything else is padding —
the reader is looking at a house, not a data dictionary.
"""

# key -> (zh, en). Keys match the payload field names the page uses.
NOTES = {
    "entry_price": (
        "该区政府估价的 25 分位——四分之一的房子在这个价位以下。"
        "这是「进得去的价」，不是均价，两者常差很多。",
        "The 25th percentile of council valuations here — a quarter of homes "
        "sit below it. This is what it costs to get in, not the average, and "
        "the two are often far apart."),
    "median_cv": (
        "区内全部计税单元的政府估价中位数，**包含公寓、商铺和工业地**。"
        "公寓密集或有工业区的郊区，这个数会明显低于「一栋住宅多少钱」。",
        "Median council valuation across ALL rating units here, including "
        "apartments, retail and industrial land. Apartment-dense and "
        "industrial suburbs read well below a residential interpretation."),
    "avg_value": (
        "对区内住宅存量做自动估值后取平均，**不是成交价**。"
        "同期全奥克兰成交中位价 $980,000，本数据集 205 个郊区的中位数是 $1,165,950——"
        "一个按成交量加权只看卖掉的，一个对每个郊区等权覆盖全部存量，不可直接比较。",
        "An automated valuation averaged across the suburb's housing stock, "
        "NOT a sale price. The regional sale median was $980,000 over the same "
        "period while the median of these is $1,165,950: one weights by what "
        "sold, the other weights every suburb equally over all stock."),
    "change_1y": (
        "估值的近一年变化，不是成交价变化。估值模型会滞后于市场。",
        "The change in estimated value over the past year, not in sale prices. "
        "A valuation model lags the market."),
    "long_term_growth": (
        "长期年化资本增长，由数据源计算。它是过去的平均，不是对未来的预测。",
        "Long-run annualised capital growth as calculated by the source. It is "
        "an average of the past, not a forecast."),
    "gross_yield": (
        "**估算**的毛租金回报：周租金中位数 × 52 ÷ 估值。"
        "扣除地税、保险、维护、空置和管理费之前的数字，净回报会低不少。",
        "An ESTIMATED gross yield: median weekly rent x 52 / estimated value. "
        "Before rates, insurance, maintenance, vacancy and management, so the "
        "net figure is considerably lower."),
    "median_rent": (
        "该区周租金中位数，跨所有户型。三房和一房的租金差得很远，"
        "详情页有按户型拆开的数字。",
        "Median weekly rent across all property sizes in the suburb. A "
        "one-bedroom and a three-bedroom differ a lot; the detail view breaks "
        "it down by bedroom count."),
    "days_to_sell": (
        "从挂牌到售出的中位天数。数字小说明卖得快，通常也意味着买方竞争激烈。",
        "Median days from listing to sale. A low number means the suburb "
        "trades quickly, which usually also means buyers compete harder."),
    "sold_12m": (
        "近 12 个月成交套数。数字大意味着选择多、可比案例多；"
        "小的郊区里单个成交对统计的影响会很大。",
        "Sales in the past 12 months. A high count means more choice and more "
        "comparable evidence; in a small suburb one sale moves the statistics "
        "a lot."),
    "cbd_km": (
        "郊区质心到 Britomart 的**直线距离**，不是车程。"
        "跨海港的郊区直线很近、开车很远。",
        "Straight-line distance from the suburb's centroid to Britomart, NOT "
        "drive time. A suburb across a harbour is close on this measure and "
        "far in a car."),
    "median_section_m2": (
        "地块面积中位数，只统计 100–5000 m² 的地块。"
        "cross-lease 公寓的地块面积记为 0，约占全部计税单元的三成，已排除在外。",
        "Median section size, counting only sections between 100 and 5,000 m2. "
        "Cross-lease flats record a land area of zero — about 30% of all rating "
        "units — and are excluded."),
    "own_section_pct": (
        "地块面积 ≥300 m² 的计税单元占比，用来估计「独立屋而非公寓」的比例。",
        "The share of rating units with a section of 300 m2 or more, as a "
        "proxy for how much of the suburb is a standalone house rather than a "
        "flat."),
    "population": (
        "来自市场数据源，不是人口普查。源站未收录的郊区为空。",
        "From the market data source, not a census. Empty where the source "
        "does not cover the suburb."),
    "traits_from_intro": (
        "从该区的维基百科开头段里读出来的特征，每一条都能在原文里找到依据。"
        "**没有某个特征只表示简介没提**，不表示那里没有。",
        "Read out of the suburb's Wikipedia opening paragraph, each one "
        "traceable to a phrase in it. An absent trait means the intro did not "
        "mention it, NOT that the suburb lacks it."),
}


def en(key):
    """The English note, for Unity Catalog column comments."""
    n = NOTES.get(key)
    return n[1] if n else None


def payload():
    """[zh, en] pairs for the page, which needs both."""
    return {k: [zh, e] for k, (zh, e) in NOTES.items()}


if __name__ == "__main__":
    for k, (zh, e) in NOTES.items():
        print(f"{k}\n  zh  {zh[:88]}\n  en  {e[:88]}\n")
