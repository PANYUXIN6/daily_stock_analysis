# A 股数据源与降级策略

本项目只维护 A 股数据链路。单一数据源失败不应直接拖垮整个分析流程；系统会在支持相同数据集的 A 股 provider 之间按配置和可用性降级。

## 数据源边界

| 数据源 | 主要用途 | 配置 |
| --- | --- | --- |
| AkShare | 日线、实时、基本面、板块等免费能力 | 默认可用 |
| Efinance | 日线、实时与部分指数能力 | 默认可用 |
| Tushare | 日线、股票列表、基本面与市场数据 | 可选 `TUSHARE_TOKEN` |
| Pytdx | A 股日线备用 | 默认可用 |
| Baostock | A 股日线备用 | 默认可用 |
| Tencent / Sina | 实时行情与已登记指数链路 | 默认可用 |
| TickFlow | A 股日线、实时、股票列表与市场增强 | 可选 `TICKFLOW_API_KEY` |


## 运行原则

- 普通 A 股日线按 `DataFetcherManager` 的已启用 provider 顺序尝试。
- 实时行情由 `REALTIME_SOURCE_PRIORITY` 控制；无效或未启用的 source 会被跳过。
- 已登记 A 股指数使用独立的 Tencent → AkShare → TickFlow 降级链，不复用普通股票优先级。
- 基本面、资金、板块等能力按各 provider 的实际支持情况返回；可选块失败时保持 fail-open。
- 缓存、熔断、超时和重试只影响对应 provider，不改变 A 股代码与字段契约。

## 推荐配置

免费起步可仅使用默认源。需要更稳定的长期任务时，按需增加：

```dotenv
TUSHARE_TOKEN=
TICKFLOW_API_KEY=
REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em
```

不要同时引入第二套同义优先级。实际可用能力可通过 `/api/v1/data-capabilities`（若当前部署启用该路由）或运行日志核对。

## 排障顺序

1. 确认输入是六位 A 股代码或已登记指数身份。
2. 检查对应 provider 是否已配置、是否支持目标数据集。
3. 查看超时、限流、熔断和降级日志。
4. 用另一个 A 股 provider 验证是否为单源故障。
5. 网络验证不可用时，先运行离线测试和代码编译检查。

市场支持边界见 [market-support.md](market-support.md)，完整环境变量见 [full-guide.md](full-guide.md)。
