# -*- coding: utf-8 -*-
"""A 股大盘复盘配置。"""

from dataclasses import dataclass
from typing import List


@dataclass
class MarketProfile:
    """大盘复盘市场区域配置"""

    region: str
    # 用于判断整体走势的指数代码
    mood_index_code: str
    # 新闻搜索关键词
    news_queries: List[str]
    # 指数点评 Prompt 提示语
    prompt_index_hint: str
    # 市场概况是否包含涨跌家数、涨停跌停
    has_market_stats: bool
    # 市场概况是否包含板块涨跌
    has_sector_rankings: bool


CN_PROFILE = MarketProfile(
    region="cn",
    mood_index_code="000001",
    news_queries=[
        "A股 大盘 复盘",
        "股市 行情 分析",
        "A股 市场 热点 板块",
    ],
    prompt_index_hint="分析上证、深证、创业板等各指数走势特点",
    has_market_stats=True,
    has_sector_rankings=True,
)

def get_profile(region: str) -> MarketProfile:
    """返回 A 股市场配置并拒绝非 CN 输入。"""
    if str(region or "cn").strip().lower() != "cn":
        raise ValueError("大盘复盘仅支持 A 股（region=cn）")
    return CN_PROFILE
