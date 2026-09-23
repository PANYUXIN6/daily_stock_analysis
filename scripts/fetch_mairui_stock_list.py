#!/usr/bin/env python3
"""Refresh the A-share CSV from Mairui; retain the stock-index CSV contract."""
from pathlib import Path
import sys

# Direct script execution and import both use the project package.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from data_provider.mairui_fetcher import MairuiFetcher

OUTPUT_DIR = ROOT / 'data'


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='获取麦蕊沪深及北交所 A 股股票列表')
    parser.parse_args(argv)
    load_dotenv(ROOT / '.env')
    try:
        frame = MairuiFetcher().stock_list()
    except Exception as exc:
        print(f'[错误] 股票列表未更新：{exc}')
        return 1
    if frame.empty:
        print('[错误] 股票列表为空，保留已有文件')
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / 'stock_list_a.csv'
    temporary = target.with_suffix('.csv.tmp')
    frame.to_csv(temporary, index=False, encoding='utf-8-sig')
    temporary.replace(target)
    print(f'已保存 {len(frame)} 只 A 股证券至 {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
