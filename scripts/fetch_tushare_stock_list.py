#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch the active A-share security list from Tushare Pro."""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

try:
    import tushare as ts
except ImportError:
    print("[错误] 未安装 tushare；请执行 pip install tushare")
    raise SystemExit(1)


OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
A_RK_BATCH_SIZE = 200
A_RK_FIELDS = "ts_code,name,close,pre_close,trade_time"
A_RK_NAME_PREFIX_RE = re.compile(r"^(XD|XR|DR|N|C)")


def get_tushare_api():
    load_dotenv()
    token = (os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        print("[错误] 请在 .env 中配置 TUSHARE_TOKEN")
        return None
    try:
        api = ts.pro_api(token)
        api.trade_cal(exchange="SSE", start_date="20240101", end_date="20240101")
        return api
    except Exception as exc:
        print(f"[错误] Tushare API 连接失败: {exc}")
        return None


def random_sleep(min_seconds: int = 5, max_seconds: int = 10) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def fetch_a_stock_list(api) -> Optional[pd.DataFrame]:
    """Fetch all currently listed Shanghai, Shenzhen, and Beijing securities."""
    try:
        frame = api.stock_basic(
            exchange="",
            list_status="L",
            fields=(
                "ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,"
                "exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type"
            ),
        )
    except Exception as exc:
        print(f"[错误] 获取 A 股列表失败: {exc}")
        return None
    if frame is None or frame.empty:
        print("[错误] A 股列表为空")
        return None
    return frame


def should_fix_a_stock_name(name: str) -> bool:
    text = str(name or "").strip()
    return bool(text and text.lower() not in {"nan", "none"} and A_RK_NAME_PREFIX_RE.match(text))


def chunk_list(items: List[str], chunk_size: int) -> List[List[str]]:
    return [items[index:index + chunk_size] for index in range(0, len(items), chunk_size)]


def fetch_rt_k_names(api, ts_codes: List[str]) -> Dict[str, str]:
    """Fetch current display names for securities with temporary status prefixes."""
    names: Dict[str, str] = {}
    batches = chunk_list(ts_codes, A_RK_BATCH_SIZE)
    for index, batch in enumerate(batches):
        try:
            frame = api.rt_k(ts_code=",".join(batch), fields=A_RK_FIELDS)
        except Exception as exc:
            print(f"[警告] rt_k 批次 {index + 1} 获取失败: {exc}")
            continue
        if frame is not None and not frame.empty:
            for _, row in frame.iterrows():
                code = str(row.get("ts_code") or "").strip()
                name = str(row.get("name") or "").strip()
                if code and name and code.lower() not in {"nan", "none"} and name.lower() not in {"nan", "none"}:
                    names[code] = name
        if index + 1 < len(batches):
            random_sleep(1, 2)
    return names


def fix_a_stock_names_with_rt_k(api, frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or not {"ts_code", "name"}.issubset(frame.columns):
        return frame
    candidates = frame.loc[frame["name"].astype(str).map(should_fix_a_stock_name), "ts_code"].astype(str).tolist()
    if not candidates:
        return frame
    names = fetch_rt_k_names(api, candidates)
    if not names:
        return frame
    fixed = frame.copy()
    for code, name in names.items():
        fixed.loc[fixed["ts_code"].astype(str) == code, "name"] = name
    return fixed


def save_to_csv(frame: pd.DataFrame, filename: str = "stock_list_a.csv", market_name: str = "A股") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"✓ {market_name}列表已保存: {path}（{len(frame)} 条）")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="获取 Tushare A 股股票列表")
    parser.add_argument("--a-rk", action="store_true", help="用 rt_k 修正临时状态前缀名称")
    args = parser.parse_args(argv)

    api = get_tushare_api()
    if api is None:
        return 1
    frame = fetch_a_stock_list(api)
    if frame is None:
        return 1
    if args.a_rk:
        frame = fix_a_stock_names_with_rt_k(api, frame)
    save_to_csv(frame)
    print(f"任务完成：共 {len(frame)} 只 A 股证券")
    return 0


if __name__ == "__main__":
    sys.exit(main())
