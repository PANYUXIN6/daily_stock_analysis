<div align="center">

# 📈 A 股智能分析系統

[![CI](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

結合行情、技術指標、新聞與大型語言模型的 A 股自選股分析工具，支援上海、深圳、北京證券交易所上市證券及已登記的 A 股指數。

[简体中文](../README.md) | [English](README_EN.md) | 繁體中文

</div>

## 功能

- 個股報告：核心結論、趨勢、關鍵價位、風險提示與操作檢查項。
- A 股大盤復盤：主要指數、市場寬度、板塊表現與次日策略。
- A 股資料降級鏈：AkShare、Tushare、Efinance、Pytdx、Baostock、騰訊與可選 TickFlow。
- 可選新聞搜尋、Web/API、本地排程、Docker、GitHub Actions 與通知推送。

主流程為：解析股票清單 → 取得行情與新聞 → 技術面及模型分析 → 產生報告 → 可選通知。後端入口是 `main.py` 與 `server.py`，Web 前端位於 `apps/dsa-web/`。

## 快速開始

```bash
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis
pip install -r requirements.txt
cp .env.example .env
python main.py --stocks 600519,000858,300750
```

至少設定一個可用的大模型渠道。行情可使用內建免費 A 股資料源；`TUSHARE_TOKEN` 與 `TICKFLOW_API_KEY` 是可選的穩定性增強。

已登記指數請使用明確代碼，例如 `sh000016`、`sz399006` 或 `930606.CSI`；一般六位代碼按 A 股證券處理。

## 常用命令

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,000858
python main.py --market-review
python main.py --schedule
python main.py --serve-only
```

## 文件

- [文件索引](INDEX.md)
- [完整設定與部署指南](full-guide.md)
- [A 股市場支援邊界](market-support.md)
- [LLM 設定指南](LLM_CONFIG_GUIDE.md)
- [更新記錄](CHANGELOG.md)

問題請透過 [GitHub Issues](https://github.com/ZhuLinsen/daily_stock_analysis/issues) 回報。

## 免責聲明

本專案僅供學習與研究，不構成任何投資建議。證券市場有風險，使用者須自行承擔使用本專案所產生的決策與損失。
