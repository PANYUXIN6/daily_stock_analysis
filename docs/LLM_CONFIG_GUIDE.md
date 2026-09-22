# DeepSeek 模型配置

本项目仅支持 DeepSeek 官方云端 API。分析、Agent 对话和图片导入共用该厂商接入。

## 快速配置

```dotenv
DEEPSEEK_API_KEY=你的密钥
LITELLM_MODEL=deepseek/deepseek-flash
VISION_MODEL=deepseek/deepseek-flash
```

`DEEPSEEK_API_KEYS` 支持逗号分隔的多个 Key，并优先于单 Key。`AGENT_LITELLM_MODEL` 留空继承主模型；`LITELLM_FALLBACK_MODELS` 支持同厂商备用模型，例如 `deepseek/deepseek-v4-pro`。`LLM_TEMPERATURE` 控制温度，`LLM_REQUEST_DELAY` 控制分析请求间隔。

DeepSeek Flash 支持图片输入；V4 Pro 用于文本。可用模型和能力以 [DeepSeek 官方文档](https://api-docs.deepseek.com/quick_start/pricing/)为准。

## Web 设置

在「设置 → AI 模型」填写 DeepSeek Key，或添加 DeepSeek 渠道，配置模型后测试连接并保存。渠道地址仅接受 `https://api.deepseek.com`（可带 `/v1`），协议为 `deepseek`，使用 Chat Completions。可对 JSON、工具调用、流式输出和图片输入执行能力检测。

## 高级路由

`LLM_CHANNELS` 可将不同 DeepSeek Key 分组；`LITELLM_CONFIG` 可加载 YAML 路由，示例见 [litellm_config.example.yaml](examples/litellm_config.example.yaml)。优先级为 YAML → 渠道 → DeepSeek 环境变量。YAML 可使用路由别名，但实际调用模型必须是 `deepseek/<model>`，不能转发至其他厂商或自建端点。

## 旧配置迁移

其他厂商的 Key、温度和模型配置已移除。请清理旧环境变量，重新填写 DeepSeek Key 和模型。旧 `GEMINI_REQUEST_DELAY` 改为 `LLM_REQUEST_DELAY`。原有报告与会话记录不删除。

## 排障

认证失败请检查 Key；模型不存在请通过官方模型列表确认名称；限流时降低并发或增加请求间隔。图片导入需使用支持图片输入的模型。测试连接会向 DeepSeek 发送测试请求，并可能产生费用。

### 问股可见对话上下文压缩

问股默认注入最近 20 条可见对话。需要为长会话节省 token 时，可开启以下 LLM 压缩配置：

```env
AGENT_CONTEXT_COMPRESSION_ENABLED=true
AGENT_CONTEXT_COMPRESSION_PROFILE=balanced

### LLM usage HMAC 遥测

P0a usage telemetry 会为实际发送的 message 生成 HMAC-SHA256 指纹，用于后续判断相同 prompt/message 前缀是否稳定。该能力只写入本地 `llm_usage` 记录，不改变 prompt、provider 参数、cache hint、模型输出或 fallback 顺序。

Usage 来源按三层读取：

- 优先读取 provider / LiteLLM 公开响应字段 `usage`。
- 其次读取 LiteLLM 公开响应字段 `usage_metadata`。
- 最后才读取 `_hidden_params["usage"]`，这是 LiteLLM private/internal 的 best-effort fallback，不是稳定公共契约；缺失时只代表 usage/cache telemetry 可能不完整，不代表模型请求失败。

Cache token 归一化只做 allowlisted best-effort normalization。外部字段依据和运行时边界如下，避免把官方稳定契约、LiteLLM 当前归一化行为和本仓库兼容 allowlist 混为一谈：

| Provider / 来源 | 读取字段 | 依据与边界 | 覆盖情况 |
| --- | --- | --- | --- |
| DeepSeek | `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | DeepSeek Chat Completion 文档说明 `prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`：<https://api-docs.deepseek.com/api/create-chat-completion> | unit/mock 覆盖；本轮清理未执行在线 API 调用 |
| LiteLLM public response shape | `usage` / `usage_metadata` | 按当前依赖窗口 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0` 的 response / `Usage` object shape 消费；不作为 LiteLLM 2.x 兼容承诺 | Analyzer / Agent / usage tests 覆盖 |
| LiteLLM private fallback | `_hidden_params["usage"]` | private/internal best-effort fallback，不是 LiteLLM 稳定公共契约；仅在 public usage zero-only/no-signal 等窄场景补足 streaming usage，不改变 provider 请求参数 | unit/mock 覆盖；缺失时只影响 telemetry 完整性，不代表模型请求失败 |

```env
LLM_USAGE_HMAC_SECRET=
LLM_USAGE_HMAC_KEY_VERSION=local-v1
```

- `LLM_USAGE_HMAC_SECRET` 留空时，系统会在数据目录生成 `.llm_usage_hmac_secret`，适合单部署本地比较。
- 只有需要跨部署比较 HMAC 时，才显式配置同一个高熵随机密钥；建议使用 `openssl rand -hex 32` 生成。
- `.llm_usage_hmac_secret` 是本地 secret artifact，已在 `.gitignore` 中按文件名忽略。
- 轮换密钥时同步更新 `LLM_USAGE_HMAC_KEY_VERSION`，避免不同密钥生成的 HMAC 被误比较。
- 不要复用登录 session secret，也不要把真实密钥提交到版本控制或暴露在 issue、日志、截图中。


### Legacy message stability audit（P0.5a）

P0.5a 在普通个股分析路径为 legacy `[system, user]` message 追加内部稳定性审计字段，继续写入本地 `llm_usage`。它复用上面的 message HMAC，不修改 prompt 内容、message 顺序、provider 请求参数、cache hint、模型输出、fallback 顺序，也不扩展公开 Usage API 或 Web 页面。

新增字段只用于维护者诊断：

- `language`、`market_group`、`analysis_mode`、`legacy_prompt_mode`、`provider`、`transport`、`message_count` 描述本次普通个股分析调用的低敏路由上下文。
- `skill_config_hmac` 是基于已解析 skill prompt 片段、默认 skill 策略和 legacy prompt 模式生成的 HMAC-SHA256，用于判断 system message 是否随 skill configuration 变化；不会保存 skill 原文。
- `known_dynamic_marker_positions` 是 JSON string，只记录 `marker_name`、`message_role`、`char_offset`；不会保存股票代码、股票名称、日期、新闻正文、行情值、headers、response text 或 prompt 片段。
- `estimated_total_prompt_tokens`、`approx_common_prefix_chars`、`approx_common_prefix_tokens` 基于项目内稳定 canonical render 估算：按 message 顺序拼接 `role + "\n" + content`，并用固定分隔符连接。该口径不声称等同 provider 真实 wire bytes。
- `char_offset` 是 marker 在对应 message `content` 内的位置；`approx_common_prefix_chars` 是 canonical render 起点到第一个已知动态 marker 之前的字符数。没有 marker 时 common-prefix 字段为 `NULL`。
- token 估算使用 `ceil(chars / 3)`，只作 diagnostics，不替代 provider usage，也不参与 cache threshold 判定；中文场景可能偏低。

P0.5a 不引入 PromptBlock IR、`block_id`、`stability_class`、`static_prefix_hash` 或 `dynamic_context_hash`。Agent、research 与 market review 路径暂不接入该审计。

---

## 用量统计

用量页仅统计 DeepSeek：总计、调用类型、模型分组和最近调用均使用同一筛选条件。已有 provider 字段以该字段为准；更早的空 provider 记录仅在模型为 `deepseek`、`deepseek/...` 或裸 `deepseek-*` 时纳入。其他厂商历史记录保留在数据库中，但不再计入或显示。
