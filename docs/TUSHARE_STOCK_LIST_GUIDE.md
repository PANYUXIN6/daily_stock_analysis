# Tushare A 股列表生成指南

仓库只生成 A 股股票列表。脚本读取 Tushare `stock_basic`，输出 `data/stock_list_a.csv`，供 Web 股票索引生成流程使用。

## 准备

```bash
pip install tushare pandas pypinyin
export TUSHARE_TOKEN=your_token
```

也可以在仓库根目录 `.env` 中配置 `TUSHARE_TOKEN`。不要把真实 Token 提交到版本库。

## 生成列表

```bash
python scripts/fetch_tushare_stock_list.py
```

如需用实时行情名称修正临时状态前缀，可增加：

```bash
python scripts/fetch_tushare_stock_list.py --a-rk
```

输出字段包括 `ts_code`、`symbol`、中文名称、英文名称与别名。脚本会对代码和名称做基础清洗，并保留上海、深圳、北京证券交易所的 A 股记录。

## 生成 Web 股票索引

```bash
python scripts/generate_index_from_csv.py --output apps/dsa-web/public/stocks.index.json
```

只更新已登记指数时使用：

```bash
python scripts/generate_index_from_csv.py --index-only
```

最终产物应只包含 `market=CN`，普通六位代码按证券处理；指数身份以 `scripts/stock_index_seeds/index_registry.csv` 为准。

## 常见问题

- `TUSHARE_TOKEN` 缺失：检查环境变量或 `.env`。
- 权限或频率限制：以 Tushare 控制台返回为准，稍后重试或调整调用频率。
- Web 搜索不到新股票：重新生成 `stocks.index.json`，然后重建 Web 前端。
