# 麦蕊迁移、字段映射与实测限制

本次替换仓库原有 Tushare HTTP/SDK 调用，并按量价波段需求移除估值和财务筛选。主分析、选股快照、选股日线、跳空涨停、股票索引与部署配置改用麦蕊；其他已有行情源继续承担 fallback。未新增数据表或修改报告/API 的字段结构。接口证书仅放在本地 `.env` 或部署密钥中。

## 配置与入口

```dotenv
MAIRUI_LICENCE=your_licence
# 可选，默认值如下，只接受 HTTPS：
# MAIRUI_BASE_URL=https://api.mairuiapi.com
# 可选，配置证书时默认 -1；数值越小越先尝试：
# MAIRUI_PRIORITY=-1
```

证书配置后，普通日线默认优先麦蕊；未显式配置实时或快照优先级时，自动加入 `mairui`。显式优先级中原 `tushare` 应改成 `mairui`。已登记指数的单标的固定来源链保持既有规则；大盘复盘原 Tushare 指数获取路径改成麦蕊指数行情。

`TUSHARE_TOKEN`、`TUSHARE_HTTP_URL`、选股模块的 `TUSHARE_API_TOKEN` / `TUSHARE_API_URL` / `TUSHARE_TRADE_DATE` / `TUSHARE_DAILY_ADJ` 以及 Tushare SDK 均退出运行态。选股独立日线适配固定使用等比前复权 `fr`，主分析日线保持原不复权契约。股票索引命令改为：

```bash
python scripts/fetch_mairui_stock_list.py
python scripts/generate_index_from_csv.py --source mairui
# 或运行完整刷新链（包括静态索引同步）：
python scripts/refresh_stock_index.py
```

输出仍为 `data/stock_list_a.csv`，保留索引实际读取的 `ts_code,symbol,name` 三列。旧 `--a-rk` 参数移除；名称直接来自麦蕊列表，现有索引生成器继续处理除权展示名前缀。原导出中的其他证券资料列不再在索引刷新时抓取（详见下表），不能把新 CSV 当作原 `stock_basic` 全字段导出。

GitHub Actions 对应配置为 secret `MAIRUI_LICENCE`，可选 variable/secret `MAIRUI_BASE_URL`。Docker 沿用现有 `.env` 注入方式。Web 设置页使用密码框保存“麦蕊接口证书”。配置未发布到任何远端，也未提交 Git。

## 代码责任边界

- `data_provider/mairui_fetcher.py`：唯一麦蕊 HTTP 传输、日线/报价/列表/快照单位转换与大盘行情适配。
- `data_provider/base.py`：注册新 provider，保留原有错误隔离与数据源 fallback。
- `src/services/screening/snapshot.py`、`daily.py`：复用适配器，保留快照缓存和来源健康状态。
- `data_provider/gap_limit_up.py`：组合交易日历、原始/等比复权行情与 `instrument` 当日涨停价。
- `src/services/screening/gap_limit_up.py`：核实当日完整跳空与收盘涨停；直接比较等比复权 OHLC，不伪造精确复权因子。

没有新增架构层；原 Tushare 适配位置由麦蕊接替。本仓库没有现成 `REPO_MAP.md` / `ARCHITECTURE.md`，本次从上述源文件确认入口与依赖，没有为了迁移另造仓库地图。

## 接口与字段映射

下表路径省略 HTTPS 域名和末尾 licence；金额在应用内部为元、日线及单股实时报价成交量为股。大盘复盘 `IndexData.volume` 保留既有“手”契约。

| 原接口/用途 | 麦蕊接口或查询组合 | 字段与单位处理 |
| --- | --- | --- |
| `stock_basic` 列表、名称 | `hslt/list` + `bj/list/all` | `dm → symbol/code`，保留交易所后缀构造原 CSV `ts_code`；`mc → name`。沪深和北交所必须都成功，避免静默丢掉北交所 |
| `fund_basic` ETF 名称 | `jj/etf` | `dm,mc → code,name` |
| `daily` 普通股票日线 | `hsstock/history/{code}/d/n`；北交所 `bj/history/{code}/d/n` | `t,o,h,l,c,v,a,pc → date,open,high,low,close,volume,amount,pre_close`；实测 `v` 为手，乘 100；`a` 为元，不再乘 1000；涨跌幅由 `c/pc-1` 计算 |
| `daily + adj_factor` 选股日线 | 同上，复权参数 `fr` | 等比前复权 OHLC 与原乘法因子调整目的相同；不使用普通加法前复权 `f` 代替 |
| `fund_daily` ETF 日线 | `jj/lskx/{code}/Day` | 量字段为股；本地过滤日期（端点实测忽略 `lt`）。样本金额全为 0，视为不可用并 fallback；不伪造金额，不把净值当成交价格 |
| `quotation` / SDK `get_realtime_quotes` | 沪深 `hsstock/real/time/{bare_code}`；北交所 `bj/stock/real/time/{bare_code}`；基金 `fd/real/time/{bare_code}` | `p,o,h,l,yc,cje,ud,pc,t` 对应原价格/金额/涨跌/时间；单股用 `pv` 原始股数，避免 `v` 手数舍入损失 |
| 实时报价补充字段 | `hsrl/ssjy/{code}` | `sz,lt` 已是元；`hs` 换手率为百分点；`lb` 实测为倍数；`sjl` 为 PB；`pe` 明确标为动态 PE，与实时报价对象的动态估值契约一致 |
| 选股 `daily + daily_basic + stock_basic` | `hsrl/real/all` + 沪深/北交所列表 | `p,pc,cje,sz,lt,lb,hs` 对应量价快照；保留 OHLC 与日期用于跳空初筛。不再查询 PE，PE/PB 空值不影响筛选或评分 |
| `trade_cal` | `tcalendar/list/{year}` | 字符串交易日数组；跨年组合后按请求范围筛选，不把休市日当交易日 |
| `index_daily` 大盘指数 | `hsindex/real/time/{code.EXCHANGE}` | 价格/金额为原单位；单标的统一对象用股，大盘复盘输出转回手；不同于旧盘后日线 fallback，此路径提供真实指数行情时间 |
| `rt_k` / `daily` 全市场宽度 | `hsrl/real/all` + 活跃证券列表 + `hslt/ztgc/{date}` / `dtgc/{date}` | 只统计列表交集、非停牌有效行；金额汇总除 1e8 得亿元；涨跌停按实际股池计数，避免给无涨跌幅限制的新股套固定比例 |
| `moneyflow_ind_ths` / `moneyflow_ind_dc` 行业排名 | 无已确认同口径的替换 | 实测 `hibk/zjhhy` 混有概念与行业，当前返回不可用，继续现有其他 provider 的行业排名 fallback |
| `stk_limit.up_limit` / 当日封板确认 | `hsstock/instrument/{code}`；北交所 `bj/instrument/{code}` | `up` 与当日不复权收盘价按分比较；核对证券身份及 `pc` 与日线前收盘价一致。跳空涨停仅筛当日新信号，不查询涨停池或历史限价；当日快照不能用于历史事件 |
| `adj_factor` 跨日缺口 | 不复权 `n` + 等比后复权 `br` 的同日 OHLC | 原始价核对涨停，`br` 价比较跨日缺口；因供应商价格按分舍入，边界差距 ≤ 0.01 复权价单位时不确认缺口；当前价基准下沿仅作为近似展示值 |

## 无法无损替代的字段与受影响策略（完整清单）

以下只列当前量价流程仍使用的字段。PE/PB、财报增长、扣非与股息率已按量价波段需求移除，其数据缺口不再影响筛选。原净利润断层改为跳空涨停，不再依赖财报索引覆盖或披露日期。

| 字段/能力 | 缺口与已尝试组合 | 影响及当前行为 |
| --- | --- | --- |
| 精确 `adj_factor` 原始数值 | `n+br` 能完成保守缺口判断，但两组价格均舍入，不能由收盘价之比反推精确因子 | **跳空涨停**：分位边界不确定则排除；前/后复权技术策略仍可使用供应商 OHLC，数值可能与原源有舍入差异 |
| `stock_basic.industry` 的原分类身份 | 麦蕊概念树、公司 `instype` 与原供应商分类不保证一一对应；不把不同分类冒充同一行业 | **均衡多因子、趋势质量、资金热度、缩量回踩、放量突破、超跌反转**的行业/主题解释、集中度约束，以及跳空涨停后续行业研究：麦蕊快照 `industry` 留空，沿用已有行业补充渠道；降级信息可见 |
| 同花顺/东财原行业指数 `industry/name,pct_change` 与分类边界 | 麦蕊 `hibk/zjhhy` 实测 496 行，包含概念板块，不能整表当行业榜；按成分股自行加权也不保证原指数算法一致 | 大盘复盘/市场结构/行业主线；使用既有其他源 fallback，无其他源时缺失，不编造排名 |
| 股票全资料 CSV：`area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type` | 新索引脚本只输出实际消费的代码/名称；其中全称、英文名、上市日等可另查公司/基础信息，但不在一次列表查询中完整提供；退市日、沪深港通资格、控制人分类等没有本次确认的同口径全量映射 | 无选股硬条件直接消费这些 CSV 列；**外部依赖完整 stock_basic CSV 的脚本需调整**。不承诺原完整导出结构仍存在 |
| 旧 `rt_k.name` 临时前缀名称修正 | 麦蕊列表给当前简称，实时券商响应无名称；没有相同修正链路。索引生成器仍保留已有除权前缀处理 | 股票索引刷新/搜索展示；无策略数值影响 |

## 当前证书实测的数据缺口（可随供应商补齐而恢复）

2026-09-22 本机 HTTPS 实测；未在文档中记录任何实际证书。

- 沪深列表 **5224** 条、北交所 **345** 条，合并 **5569** 只 A 股。网络全市场响应 5914 条，经股票列表交集为 **5569** 条；选股沿用已有的有效正价格过滤后为 **5555** 条。
- `000001` 券商实时 `pv=75945732` 股、`v=759457` 手；网络行情 `v=75.95`，实际为舍入后的万手，与网页标注的“手”不一致。实时使用 `pv`；历史 `v=759457` 手转为 75945700 股，存在供应商按手舍入的精度差异。
- 跳空涨停当晚筛选当日量价新信号，使用 `instrument.up`，不依赖历史限价或涨停池。历史限价抽样缺近期日期不再阻塞该场景。市场统计仍使用涨跌停池计数，与此策略独立。
- 2026-09-23 本机实测沪深及北交所 `instrument` 均有 `ei,ii,pc,up`。接口没有交易日字段；例如 `600519.SH` 响应的前收盘价与最新日线不一致，程序据此拒绝未对齐数据。晚上仅使用当日日线与匹配的证券基础信息，不将旧快照当作当日证据。
- ETF `510050` 历史 K 线返回 **1023** 条且样本成交额全部为 0；`hsstock/history/510050.SH` 返回数据不存在。ETF 历史成交额无法通过当前响应可靠补齐，适配器触发原有其他源 fallback。A 股筛选策略不以 ETF 为候选。
- 沪深券商单股实时路径要求裸代码；样本 `000001.SZ` 返回资源不存在、`000001` 正常。历史行情仍使用带交易所代码，避免股票/指数同码冲突。

重评条件：供应商补齐行业分类、可靠同步的当日限价或 ETF 金额字段，再补契约样本和验证后扩大覆盖。当前不放宽封板或缺口条件。

## 验证与回滚

测试集中在 `tests/test_mairui_fetcher.py` 和原有配置、行情管理、选股、跳空涨停测试，覆盖股/手/元、跨交易所代码、无效/限流响应、证书 URL 脱敏、当日限价及复权舍入边界。以下为接口迁移阶段的验证记录；后续量价范围调整见[量价波段分析](price-volume-trading.md)：

- `./scripts/ci_gate.sh`：语法、关键 flake8 与确定性检查通过；pytest **5018 passed、409 subtests passed、7 failed**。这 7 项在隔离的未修改 HEAD 中同样复现：两项 context-pack 文档断言、四项实时指标上下文断言、一项 macOS 调度子进程清理断言；本次迁移没有修复这些既有问题。
- Web：`npm ci --offline --no-audit --no-fund`、`npm run lint`、`npm run build` 完成；lint 为 0 errors、2 条既有 Hook 警告；SettingsPage 与 StockScreeningPage 的 **81 项测试通过**。
- 本地真实 HTTPS 抽样覆盖股票列表、沪深/北交所日线、前复权、快照、单股实时、六个指数、市场统计、财务指标及缺口行情组合。未运行完整全市场跳空涨停在线扫描，未执行真实 LLM 分析或通知，未在 Docker / GitHub Actions 远端验证。
- 未取得页面截图：本地预览需要的自动审批连续两次超时，浏览器进程未启动；替代证据为真实页面组件测试、类型检查及构建。Web 仅更换供应商标签与帮助文案。
- 中英文现有配置、部署与 FAQ 已同步；本专题细节文档为中文，英文索引已明确标注 Chinese-only。



以上是接口迁移与行为验证，不表示缺失字段已被补齐，也不是策略历史收益验证。

回滚无需数据迁移：恢复本次代码/文档差异并恢复旧部署配置即可；仅需临时禁用麦蕊时清空 `MAIRUI_LICENCE`，显式优先级列表同步去掉 `mairui`，系统继续其他行情源。跳空涨停仍需支持当日准确限价的行情源。

官方参考：[沪深 A 股](https://www.mairui.club/hsdata)、[沪深指数](https://www.mairui.club/hszsdata)、[沪深数据中心](https://www.mairui.club/hanalyse)、[北交所](https://www.mairui.club/bjdata)、[基金行情](https://www.mairui.club/jjhqdata)。
