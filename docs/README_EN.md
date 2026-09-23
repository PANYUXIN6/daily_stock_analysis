<div align="center">

# 📈 A-Share Intelligent Analysis System

[![CI](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

An A-share watchlist analysis tool combining market data, technical indicators, news, and LLM-generated reports. It supports securities listed in Shanghai, Shenzhen, and Beijing, plus registered A-share indices.

English | [简体中文](../README.md) | [繁體中文](README_CHT.md)

</div>

## Features

- Stock reports with conclusions, trend, price levels, risk alerts, and action checks.
- A-share market recaps covering indices, breadth, sectors, and next-session strategy.
- A-share data fallback across AkShare, Mairui, Efinance, Pytdx, Baostock, Tencent, and optional TickFlow.
- Optional news search through supported providers.
- Web, API, scheduler, Docker, GitHub Actions, and notification workflows.

The main flow is: parse symbols → fetch market/news data → run technical and LLM analysis → render reports → optionally notify. Backend entry points are `main.py` and `server.py`; the Web app is under `apps/dsa-web/`.

## Quick Start

```bash
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis
pip install -r requirements.txt
cp .env.example .env
python main.py --stocks 600519,000858,300750
```

Configure at least one supported LLM provider. Market data can run with the bundled free A-share providers; `MAIRUI_LICENCE` and `TICKFLOW_API_KEY` are optional stability enhancements.

Use explicit registered index identities such as `sh000016`, `sz399006`, or `930606.CSI`. Plain six-digit codes are treated as A-share securities.

## Common Commands

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,000858
python main.py --market-review
python main.py --schedule
python main.py --serve-only
```

## Documentation

- [Documentation index](INDEX_EN.md)
- [Full configuration and deployment guide](full-guide_EN.md)
- [A-share support boundary](market-support.md)
- [LLM configuration](LLM_CONFIG_GUIDE_EN.md)
- [Changelog](CHANGELOG.md)

Please use [GitHub Issues](https://github.com/ZhuLinsen/daily_stock_analysis/issues) for bug reports and questions.

## Disclaimer

This project is for learning and research only and does not constitute investment advice. You are responsible for any decisions and losses arising from its use.
