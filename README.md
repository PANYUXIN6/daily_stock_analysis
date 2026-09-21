<div align="center">

# 📈 A 股智能分析系统

[![CI](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

基于行情、技术指标、新闻与大模型的 A 股自选股分析工具，支持上海、深圳、北京证券交易所上市证券及已登记的 A 股指数。

[功能](#功能) · [快速开始](#快速开始) · [常用命令](#常用命令) · [文档](#文档)

简体中文 | [English](docs/README_EN.md) | [繁體中文](docs/README_CHT.md)

</div>

## 功能

- 个股分析：生成核心结论、趋势、关键价位、风险提示和操作检查项。
- A 股大盘复盘：汇总主要指数、市场宽度、板块表现与次日策略。
- 数据聚合：复用 AkShare、Tushare、Efinance、Pytdx、Baostock、腾讯与 TickFlow 等 A 股数据源，并按可用性降级。
- 新闻与公告：支持 Anspire、博查、Tavily、SerpAPI、Brave、MiniMax 和 SearXNG 等可选搜索服务。
- Web / API：支持任务提交、进度、历史报告、回测和配置管理。
- 自动化通知：支持 GitHub Actions、本地调度、Docker，以及企业微信、飞书、Telegram、Discord、Slack 和邮件。

项目主流程是：股票列表解析 → 行情与新闻获取 → 技术面和大模型分析 → 报告生成 → 可选通知。后端入口集中在 `main.py` 与 `server.py`，Web 前端位于 `apps/dsa-web/`。

## 快速开始

```bash
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis
pip install -r requirements.txt
cp .env.example .env
python main.py --stocks 600519,000858,300750
```

至少配置一个可用的大模型渠道。以 Gemini 为例：

```dotenv
GEMINI_API_KEY=your_key
STOCK_LIST=600519,000858,300750
```

行情默认可使用免费 A 股数据源。需要更稳定的历史行情时，可选配置 `TUSHARE_TOKEN` 或 `TICKFLOW_API_KEY`。新闻搜索也是可选能力；不配置时系统会在能力边界内降级运行。

已登记指数请使用明确的指数代码，例如 `sh000016`、`sz399006`、`930606.CSI`。普通六位代码按 A 股证券处理。

## 常用命令

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,000858
python main.py --market-review
python main.py --schedule
python main.py --serve
python main.py --serve-only
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Web 工作台启动后默认访问 `http://127.0.0.1:8000`。

## GitHub Actions

Fork 仓库后，在 `Settings → Secrets and variables → Actions` 中配置：

- 一个模型密钥，例如 `GEMINI_API_KEY`、`OPENAI_API_KEY` 或其他受支持渠道；
- `STOCK_LIST`，例如 `600519,000858,300750`；
- 至少一个通知渠道（如果需要自动推送）；
- 可选的行情与搜索服务密钥。

然后在 Actions 页面启用并手动运行“每日股票分析”工作流。具体变量、调度和部署方式见完整指南。

## 验证

```bash
./scripts/ci_gate.sh
python -m pytest -m "not network"

cd apps/dsa-web
npm ci
npm run test
npm run lint
npm run build
```

## 文档

- [文档索引](docs/INDEX.md)
- [完整配置与部署指南](docs/full-guide.md)
- [A 股市场支持边界](docs/market-support.md)
- [LLM 配置指南](docs/LLM_CONFIG_GUIDE.md)
- [更新记录](docs/CHANGELOG.md)

问题反馈请使用 [GitHub Issues](https://github.com/ZhuLinsen/daily_stock_analysis/issues)。

## License

[MIT License](LICENSE) © 2026 ZhuLinsen

## 免责声明

本项目仅供学习和研究使用，不构成任何投资建议。证券市场有风险，投资需谨慎；使用本项目造成的损失由使用者自行承担。
