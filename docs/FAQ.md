# ❓ 常见问题解答 (FAQ)

本文档整理了用户在使用过程中遇到的常见问题及解决方案。

---

## 📊 数据相关

### Q1: 报告中"量比"字段显示为空或 N/A？

**现象**：分析报告中量比数据缺失，影响 AI 对缩放量的判断。

**原因**：默认的某些实时行情源（如新浪接口）不提供量比字段。

**解决方案**：
1. 已在 v2.3.0 修复，腾讯接口现已支持量比解析
2. 推荐配置实时行情源优先级：
   ```bash
   REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em
   ```
3. 系统已内置 5 日均量计算作为兜底逻辑

> 📌 相关 Issue: [#155](https://github.com/ZhuLinsen/daily_stock_analysis/issues/155)

---

### Q3: 麦蕊获取数据失败或证书无权限？

确认 `MAIRUI_LICENCE` 与官方证书一致且未过期。全市场行情需要相应版本权限；空数据、权限失败与缺失字段会进入现有 fallback，不会改用不等价字段。无证书时可使用其他免费行情源，净利润断层需要麦蕊财务证据。详见 [迁移与实测限制](mairui-migration.md)。

---

### Q4: 数据获取被限流或返回为空？

**现象**：日志显示 `熔断器触发` 或数据返回 `None`，或出现 `RemoteDisconnected`、`push2his.eastmoney.com` 连接被关闭等

**原因**：免费数据源（东方财富、新浪等）有反爬机制，短时间大量请求会被限流。

**解决方案**：
1. 系统已内置多数据源自动切换和熔断保护
2. 减少自选股数量，或增加请求间隔
3. 避免频繁手动触发分析
4. 若东财接口频繁失败，可设置 `ENABLE_EASTMONEY_PATCH=true` 启用东财补丁（注入 NID 令牌与随机 User-Agent，降低被限流概率）
5. 将 `MAX_WORKERS=1` 改为串行获取，减少对东财的并发压力

---

## ⚙️ 配置相关

### Q5: GitHub Actions 运行失败，提示找不到环境变量？

**现象**：Actions 日志显示 `DEEPSEEK_API_KEY` 或 `STOCK_LIST` 未定义

**原因**：GitHub 区分 `Secrets`（加密）和 `Variables`（普通变量），配置位置不对会导致读取失败。

**解决方案**：
1. 进入仓库 `Settings` → `Secrets and variables` → `Actions`
2. **Secrets**（点击 `New repository secret`）：存放敏感信息
   - `DEEPSEEK_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - 各类 Webhook URL
3. **Variables**（点击 `Variables` 标签）：存放非敏感配置
   - `STOCK_LIST`
   - `LITELLM_MODEL`
   - `REPORT_TYPE`

> 兼容说明：每日分析 workflow 也会绑定名为 `STOCK_LIST` 的 Environment，因此误把 `STOCK_LIST` 填到该 Environment variables 中也能被读取；但推荐位置仍是 Repository variables。除非你希望每日任务等待人工审批，否则不要给该 Environment 配置 required reviewers、wait timer 或部署分支限制。

---

### Q6: 修改 .env 文件后配置没有生效？

**解决方案**：
1. 确保 `.env` 文件位于项目根目录
2. **Docker 部署 / WebUI 系统设置**：
   - `--env-file .env` / Compose `env_file` 只会把宿主机 `.env` 作为启动环境变量注入容器，不会自动创建或回写容器内 `/app/.env`
   - WebUI 设置页会在当前活跃 `.env` 文件缺少某些键时展示启动注入的同名环境变量作为兜底；但“导出 `.env`”仍只导出当前活跃配置文件内容
   - WebUI 保存后的 `STOCK_LIST`、`SCHEDULE_ENABLED`、`SCHEDULE_TIME`、`SCHEDULE_TIMES`、`SCHEDULE_RUN_IMMEDIATELY`、`RUN_IMMEDIATELY` 会写回容器内的 `.env`
   - WebUI 保存后会触发当前进程的配置重载；运行中的读取路径会同步使用最新写回的 `.env`，例如定时任务会继续热读取保存后的 `STOCK_LIST`
   - 如果容器启动命令里传入了这些同名环境变量（如 `--env-file .env`、`docker run -e ...` 或 Compose `environment:`），后续重启时仍可能以启动环境变量为准；要让 WebUI 保存值接管，请同步更新或移除这些同名 override
   - 如需持久化 WebUI 保存的配置，请将 `ENV_FILE` 指向 `/app/data/runtime.env` 等可写数据卷文件，不要把宿主机 `.env` 单文件挂载到 `/app/.env`
   - `SCHEDULE_ENABLED`、`SCHEDULE_TIME`、`SCHEDULE_TIMES` 保存后会让 WebUI/API 长运行进程按新配置启停或重建 runtime scheduler；重启 `--serve-only` 进程时会恢复已启用的 daily jobs，但不会在启动时立即执行分析
   - `SCHEDULE_RUN_IMMEDIATELY` 与 `RUN_IMMEDIATELY` 仍属于启动期/一次性运行配置，保存后不会立即触发一次分析
3. **Docker 手工改 `.env` 后**：修改后仍建议重启容器
   ```bash
   docker-compose down && docker-compose up -d
   ```
4. **GitHub Actions**：`.env` 文件不生效，必须在 Secrets/Variables 中配置
5. 检查是否有多个 `.env` 文件（如 `.env.local`）导致覆盖

---

### Q7: 如何配置代理访问 DeepSeek API？

**解决方案**：

在 `.env` 中配置：
```bash
USE_PROXY=true
PROXY_HOST=127.0.0.1
PROXY_PORT=10809
```

> ⚠️ 注意：代理配置仅对本地运行生效，GitHub Actions 环境无需配置代理。

---

### LLM 配置常见问题

> 完整说明见 [LLM 配置指南](LLM_CONFIG_GUIDE.md)。

**Q: 配置了 DEEPSEEK_API_KEY 和 LLM_CHANNELS，为什么只用渠道？**

系统按优先级只取一种：高级模型路由 YAML（`LITELLM_CONFIG`）> `LLM_CHANNELS` > legacy keys。但 YAML 仅在文件可正常解析且产出了有效 `model_list` 时才生效；如果 YAML 路径无效或内容为空，系统会自动回退到 `LLM_CHANNELS` 或 legacy keys。一旦某一层级实际生效，更低优先级的配置不参与解析。

**Q: check_env 输出“未配置可用 AI 模型”怎么办？**

填写 DeepSeek API Key；如果需要固定主模型，再补 `LITELLM_MODEL=deepseek/deepseek-flash`；如果要多模型切换，再配置 `LLM_CHANNELS` 或高级模型路由 YAML。运行 `python scripts/check_env.py --config` 校验配置，`python scripts/check_env.py --llm` 实际调用 API 测试。

**Q: 如何配置多个模型？**

使用 `DEEPSEEK_API_KEYS` 配置多 Key，使用 `LITELLM_FALLBACK_MODELS` 配置 DeepSeek 备用模型。详见 [模型配置](LLM_CONFIG_GUIDE.md)，其他厂商配置已不再支持。

---

## 📱 推送相关

### Q8: 机器人推送失败，提示消息过长？

**现象**：分析成功但未收到推送，日志显示 400 错误或 `Message too long`

**原因**：不同平台消息长度限制不同：
- 企业微信：4KB
- 飞书：20KB
- 钉钉：20KB

**解决方案**：
1. **自动分块**：最新版本已实现长消息自动切割
2. **单股推送模式**：设置 `SINGLE_STOCK_NOTIFY=true`，每分析完一只股票立即推送
3. **精简报告**：设置 `REPORT_TYPE=simple` 使用精简格式
4. **仅落盘本地报告**：即使未配置任何通知渠道，`SINGLE_STOCK_NOTIFY=true` 仍会把单股报告保存到 `reports/report_YYYYMMDD_<股票代码>.md`

---

### Q8.1: 分析结束了，但 `reports/` 里没有生成报告文件？

**常见原因**：
1. `STOCK_LIST` 为空，且本轮未启用大盘复盘
2. 股票列表非空，但个股分析全部失败，最终没有成功结果
3. 个股结果已生成，但写入 `reports/` 时失败（如目录权限或挂载问题）

**现在的行为**：
1. CLI 启动分析会对上述场景显式记录失败原因
2. 非 `--serve` 的独立运行模式会返回非零退出码，避免工作流把“未生成报告”误判为成功
3. 若是单股推送模式且通知未配置，仍会继续保存本地 Markdown 报告用于排查

### Q9: Telegram 推送收不到消息？

**解决方案**：
1. 确认 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 都已配置
2. 获取 Chat ID 方法：
   - 给 Bot 发送任意消息
   - 访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - 在返回的 JSON 中找到 `chat.id`
3. 确保 Bot 已被添加到目标群组（如果是群聊）
4. 本地运行时需要能访问 Telegram API（可能需要代理）

---

### Q10: 企业微信 Markdown 格式显示不正常？

**解决方案**：
1. 企业微信对 Markdown 支持有限，可尝试设置：
   ```bash
   WECHAT_MSG_TYPE=text
   ```
2. 这将发送纯文本格式的消息

---

## 🤖 AI 模型相关

### Q11: DeepSeek API 返回 429 错误（请求过多）？

使用 DeepSeek 官方 API，详见 [模型配置](LLM_CONFIG_GUIDE.md)。限流时增加 `LLM_REQUEST_DELAY` 或降低并发。

### Q12: 如何使用 DeepSeek 模型？

使用 DeepSeek 官方 API，详见 [模型配置](LLM_CONFIG_GUIDE.md)。限流时增加 `LLM_REQUEST_DELAY` 或降低并发。

# 不需要配置 DEEPSEEK_API_KEY
DEEPSEEK_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
# deepseek-chat / deepseek-reasoner 仍兼容，但官方已标记为 2026/07/24 后废弃
```

支持的模型服务：
- DeepSeek: `https://api.deepseek.com`
- 通义千问: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Moonshot: `https://api.moonshot.cn/v1`

---

## 🐳 Docker 相关

### Q13: Docker 容器启动后立即退出？

**解决方案**：
1. 查看容器日志：
   ```bash
   docker logs <container_id>
   ```
2. 常见原因：
   - 环境变量未正确配置
   - `.env` 文件格式错误（如有多余空格）
   - 依赖包版本冲突

---

### Q14: Docker 中 API 服务无法访问？

**解决方案**：
1. 确保启动命令包含 `--host 0.0.0.0`（不能是 127.0.0.1）
2. 检查端口映射是否正确：
   ```yaml
   ports:
     - "8000:8000"
   ```

---

### Q14.1: Docker 中网络/DNS 解析失败（如 api.mairuiapi.com、searchapi.eastmoney.com 无法解析）？

**现象**：日志显示 `Temporary failure in name resolution` 或 `NameResolutionError`，股票数据 API 和大模型 API 均无法访问。

**原因**：自定义 bridge 网络下，容器使用 Docker 内置 DNS，在旁路由、特定网络环境时可能解析失败。

**解决方案**（按优先级尝试）：

1. **显式配置 DNS**：在 `docker/docker-compose.yml` 的 `x-common` 下添加：
   ```yaml
   dns:
     - 223.5.5.5
     - 119.29.29.29
     - 8.8.8.8
   ```
   然后执行 `docker-compose down` 和 `docker-compose up -d --force-recreate` 重新创建容器。

2. **改用 host 网络模式**：若上述仍无效，可在 `server` 服务下添加 `network_mode: host`，并移除 `ports` 映射。使用 host 模式时，`ports` 无效，**端口由 `command` 中的 `--port` 指定**。若宿主机默认端口已占用，可修改为其他端口（如 `.env` 中设置 `API_PORT=8080`），访问对应 `http://localhost:8080`。

> 📌 相关 Issue: [#372](https://github.com/ZhuLinsen/daily_stock_analysis/issues/372)

---

### Q14.2: Docker 安装时，软件版本号写在哪个文件里？

**结论**：对 Docker 用户来说，**最权威的版本不是某个 Python 源文件常量，而是你实际使用的镜像 tag**。

**为什么**：
1. 仓库的 Docker 发布由 `.github/workflows/docker-publish.yml` 触发，只有推送 `v*.*.*` 形式的 Git tag（例如 `v3.12.0`）时才会生成对应发布镜像。
2. 这意味着 Docker 镜像版本本质上跟随 **GitHub Release / Git tag**，而不是写死在 `main.py`、`server.py` 或其他后端源码里。
3. `apps/dsa-web/package.json` 里的 `version` 当前是占位值 `0.0.0`，WebUI “版本信息”卡片更适合用来确认静态资源是否已重建，不应当作 Docker 发布版本。

**怎么查当前 Docker 版本**：
1. **先看部署命令或 Compose 文件里的镜像 tag**：例如 `ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0`，其中 `v3.12.0` 就是当前部署版本。
2. **如果你拉的是 `latest`**：请回看当时的 `docker pull` / `docker-compose.yml` / 部署脚本，或对照 [GitHub Releases](https://github.com/ZhuLinsen/daily_stock_analysis/releases) 确认对应发布记录。
3. **如果只是想确认前端是否更新到新构建**：可以打开 WebUI 的“系统设置”页查看 `构建标识` / `构建时间`；这能帮助确认静态资源是否刷新，但不等同于 Docker 镜像发布版本。

**建议**：如果你想避免重复更新，部署时尽量固定使用明确的版本 tag（如 `v3.12.0`），不要长期依赖 `latest`。

---


## 🔧 其他问题

### Q16: 如何只运行大盘复盘，不分析个股？

**方法**：
```bash
# 本地运行
python main.py --market-only

# GitHub Actions
# 手动触发时选择 mode: market-only
```

---

### Q17: 分析结果中买入/观望/卖出数量统计不对？

**原因**：早期版本使用正则匹配统计，可能与实际建议不一致。

**解决方案**：已在最新版本中修复，AI 模型现在会直接输出 `decision_type` 字段用于准确统计。

---

### Q18: 为什么周末在 GitHub Actions 手动触发仍显示“非交易日跳过”？

**现象**：已经配置了 `TRADING_DAY_CHECK_ENABLED` 或希望手动运行，但日志仍提示“今日所有相关市场均为非交易日，跳过执行”。

**解决方案**：
1. 打开 `Actions → 每日股票分析 → Run workflow`
2. 手动触发时将 `force_run` 设为 `true`（单次强制运行）
3. 如果希望长期关闭交易日检查，在 `Settings → Secrets and variables → Actions` 中设置：
   ```bash
   TRADING_DAY_CHECK_ENABLED=false
   ```

**规则说明**：
- `TRADING_DAY_CHECK_ENABLED=true` 且 `force_run=false`：非交易日跳过（默认）
- `force_run=true`：本次即使非交易日也执行
- `TRADING_DAY_CHECK_ENABLED=false`：定时和手动都不做交易日检查

---

## 💬 还有问题？

如果以上内容没有解决你的问题，欢迎：
1. 查看 [完整配置指南](full-guide.md)
2. 搜索或提交 [GitHub Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)
3. 查看 [更新日志](CHANGELOG.md) 了解最新修复

---

*最后更新：2026-08-03*
