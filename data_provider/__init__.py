# -*- coding: utf-8 -*-
"""
===================================
数据源策略层 - 包初始化
===================================

本包实现策略模式管理多个数据源，实现：
1. 统一的数据获取接口
2. 自动故障切换
3. 防封禁流控策略

数据源优先级（动态调整）：
【配置了 MAIRUI_LICENCE 时】
1. MairuiFetcher (Priority -1) - 🔥 最高优先级（动态提升）
2. EfinanceFetcher (Priority 0) - 来自 efinance 库
3. AkshareFetcher (Priority 1) - 来自 akshare 库
4. PytdxFetcher (Priority 2) - 来自 pytdx 库（通达信）
5. BaostockFetcher (Priority 3) - 来自 baostock 库
6. TencentFetcher (Priority 5) - 腾讯直连日 K 最终兜底

【未配置 MAIRUI_LICENCE 时】
1. EfinanceFetcher (Priority 0) - 最高优先级，来自 efinance 库
2. AkshareFetcher (Priority 1) - 来自 akshare 库
3. PytdxFetcher (Priority 2) - 来自 pytdx 库（通达信）
4. BaostockFetcher (Priority 3) - 来自 baostock 库
5. TencentFetcher (Priority 5) - 腾讯直连日 K 最终兜底

提示：优先级数字越小越优先，同优先级按初始化顺序排列
"""

from .base import BaseFetcher, DataFetcherManager
from .efinance_fetcher import EfinanceFetcher
from .tencent_fetcher import TencentFetcher
from .akshare_fetcher import AkshareFetcher
from .mairui_fetcher import MairuiFetcher
from .pytdx_fetcher import PytdxFetcher
from .baostock_fetcher import BaostockFetcher

__all__ = [
    'BaseFetcher',
    'DataFetcherManager',
    'EfinanceFetcher',
    'TencentFetcher',
    'AkshareFetcher',
    'MairuiFetcher',
    'PytdxFetcher',
    'BaostockFetcher',
]
