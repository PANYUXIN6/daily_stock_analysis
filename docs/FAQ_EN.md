# Frequently Asked Questions (FAQ)

This document compiles common issues encountered by users and their solutions.

---

## Data Related

### Q1: "Volume Ratio" field shows empty or N/A in reports?

**Symptom**: Volume ratio data missing in analysis reports, affecting AI's judgment on volume changes.

**Cause**: Some default real-time quote sources (e.g., Sina interface) don't provide volume ratio field.

**Solution**:
1. Fixed in v2.3.0, Tencent interface now supports volume ratio parsing
2. Recommended real-time quote source priority:
   ```bash
   REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em
   ```
3. System has built-in 5-day average volume calculation as fallback

> Related Issue: [#155](https://github.com/ZhuLinsen/daily_stock_analysis/issues/155)

---

### Q3: Tushare data fetch failed, showing Token error?

**Symptom**: Log shows `Tushare data fetch failed: Your token is incorrect, please verify`

**Solution**:
1. **No Tushare account**: No need to configure `TUSHARE_TOKEN`, system will automatically use free data sources (AkShare, Efinance)
2. **Have Tushare account**: Verify Token is correct, check in [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638) personal center
3. All core features of this project work normally without Tushare

---

### Q4: Data fetch rate-limited or returning empty?

**Symptom**: Log shows `Circuit breaker triggered` or data returns `None`

**Cause**: Free data sources (Eastmoney, Sina, etc.) have anti-scraping mechanisms, high-frequency requests get rate-limited.

**Solution**:
1. System has built-in multi-source auto-switching and circuit breaker protection
2. Reduce watchlist size, or increase request intervals
3. Avoid frequently manually triggering analysis

---

## Configuration Related

### Q5: GitHub Actions run failed, showing environment variable not found?

**Symptom**: Actions log shows `DEEPSEEK_API_KEY` or `STOCK_LIST` undefined

**Cause**: GitHub distinguishes `Secrets` (encrypted) and `Variables` (regular variables), wrong configuration location causes read failure.

**Solution**:
1. Go to repo `Settings` → `Secrets and variables` → `Actions`
2. **Secrets** (click `New repository secret`): Store sensitive information
   - `DEEPSEEK_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - Various Webhook URLs
3. **Variables** (click `Variables` tab): Store non-sensitive configuration
   - `STOCK_LIST`
   - `LITELLM_MODEL`
   - `REPORT_TYPE`

> Compatibility note: the daily analysis workflow also binds the `STOCK_LIST` environment, so a `STOCK_LIST` value mistakenly added under that Environment's variables can still be read. Repository variables remain the recommended location. Unless you want the daily job to wait for manual approval, do not add required reviewers, wait timers, or deployment branch restrictions to this Environment.

---

### Q6: Configuration not taking effect after modifying .env file?

**Solution**:
1. Ensure `.env` file is in project root directory
2. **Docker deployment / WebUI Settings**:
   - `--env-file .env` / Compose `env_file` only injects the host `.env` as startup environment variables; it does not create or write back to `/app/.env` inside the container
   - When the active `.env` file does not contain a key, the WebUI Settings page falls back to showing the same key from startup-injected environment variables; the raw `.env` export still contains only the active config file content
   - WebUI saves `STOCK_LIST`, `SCHEDULE_ENABLED`, `SCHEDULE_TIME`, `SCHEDULE_TIMES`, `SCHEDULE_RUN_IMMEDIATELY`, and `RUN_IMMEDIATELY` back into the container's `.env`
   - Saving from WebUI triggers a config reload for the current process, and runtime reads continue from the latest persisted `.env`; for example, scheduled runs keep hot-reading the saved `STOCK_LIST`
   - If you pass the same keys as startup env vars (`--env-file .env`, `docker run -e ...`, or Compose `environment:`), those startup values can still win on later restarts; update or remove the same-name overrides if you want the WebUI-saved `.env` values to take over
   - To persist WebUI-saved config, point `ENV_FILE` at a writable data-volume file such as `/app/data/runtime.env`; do not bind-mount the host `.env` as a single file over `/app/.env`
   - Saving `SCHEDULE_ENABLED`, `SCHEDULE_TIME`, or `SCHEDULE_TIMES` starts, stops, or rebuilds the runtime scheduler in long-running WebUI/API processes; restarting a `--serve-only` process restores enabled daily jobs without immediately running an analysis at startup
   - `SCHEDULE_RUN_IMMEDIATELY` and `RUN_IMMEDIATELY` remain startup/one-shot settings; saving them does not immediately trigger an analysis run
3. **Manual `.env` edits in Docker**: Restart the container after changes
   ```bash
   docker-compose down && docker-compose up -d
   ```
4. **GitHub Actions**: `.env` file doesn't work, must configure in Secrets/Variables
5. Check if there are multiple `.env` files (e.g., `.env.local`) causing override

---

### Q7: How to configure proxy to access DeepSeek API?

**Solution**:

Configure in `.env`:
```bash
USE_PROXY=true
PROXY_HOST=127.0.0.1
PROXY_PORT=10809
```

> Note: Proxy configuration only works for local runs, GitHub Actions environment doesn't need proxy.

---

### LLM Configuration

> Full details: [LLM Config Guide](LLM_CONFIG_GUIDE_EN.md).

**Q: Configured both DEEPSEEK_API_KEY and LLM_CHANNELS, why does it only use channels?**

The system uses exactly one mode by priority: advanced YAML routing (`LITELLM_CONFIG`) > `LLM_CHANNELS` > legacy keys. However, YAML routing only takes effect when the file can be parsed successfully and yields a non-empty `model_list`; if the YAML path is invalid or the content is empty, the system automatically falls back to `LLM_CHANNELS` or legacy keys. Once a tier is active, lower-priority tiers are not used.

**Q: check_env says no usable AI model is configured, what should I do?**

Start with a DeepSeek API key. If you want to pin a primary model, add `LITELLM_MODEL=deepseek/deepseek-flash`. If you need multi-model switching, configure `LLM_CHANNELS` or advanced YAML routing. Run `python scripts/check_env.py --config` to validate config and `python scripts/check_env.py --llm` to actually call the API.

**Q: How do I configure multiple models?**

Use DeepSeek models with `DEEPSEEK_API_KEYS` and `LITELLM_FALLBACK_MODELS`. See [LLM configuration](LLM_CONFIG_GUIDE_EN.md). Other vendors are no longer supported.

---

## Push Notification Related

### Q8: Bot push failed, showing message too long?

**Symptom**: Analysis succeeded but no notification received, log shows 400 error or `Message too long`

**Cause**: Different platforms have different message length limits:
- WeChat Work: 4KB
- Feishu: 20KB
- DingTalk: 20KB

**Solution**:
1. **Auto-chunking**: Latest version implements automatic long message splitting
2. **Single stock push mode**: Set `SINGLE_STOCK_NOTIFY=true`, push immediately after each stock analysis
3. **Brief report**: Set `REPORT_TYPE=simple` for simplified format
4. **Local file fallback**: Even with no notification channel configured, `SINGLE_STOCK_NOTIFY=true` still saves each stock report to `reports/report_YYYYMMDD_<stock_code>.md`

---

### Q8.1: Analysis finished, but no report file was created under `reports/`?

**Common causes**:
1. `STOCK_LIST` is empty and market review was not enabled for this run
2. The stock list is non-empty, but every stock analysis failed so no successful result was produced
3. Stock results were produced, but writing to `reports/` failed (for example due to permissions or mount issues)

**Current behavior**:
1. CLI-triggered analysis now logs the exact failure reason for these cases
2. Standalone non-`--serve` runs now return a non-zero exit code so workflows do not treat “no report generated” as success
3. In single-stock push mode, local Markdown report saving still happens even when notifications are not configured

### Q9: Not receiving Telegram push messages?

**Solution**:
1. Confirm both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured
2. How to get Chat ID:
   - Send any message to the Bot
   - Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Find `chat.id` in the returned JSON
3. Ensure Bot has been added to target group (if group chat)
4. When running locally, need to be able to access Telegram API (may need proxy)

---

### Q10: WeChat Work Markdown format not displaying correctly?

**Solution**:
1. WeChat Work has limited Markdown support, try setting:
   ```bash
   WECHAT_MSG_TYPE=text
   ```
2. This will send plain text format messages

---

## AI Model Related

### Q11: DeepSeek API returns 429 error (too many requests)?

Use the official DeepSeek API. See [configuration](LLM_CONFIG_GUIDE_EN.md). For rate limits, increase `LLM_REQUEST_DELAY` or reduce concurrency.

### Q12: How to use DeepSeek models?

Use the official DeepSeek API. See [configuration](LLM_CONFIG_GUIDE_EN.md). For rate limits, increase `LLM_REQUEST_DELAY` or reduce concurrency.

# No need to configure DEEPSEEK_API_KEY
DEEPSEEK_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
# deepseek-chat / deepseek-reasoner remain compatible, but DeepSeek marks them deprecated after 2026/07/24
```

Supported model services:
- DeepSeek: `https://api.deepseek.com`
- Qwen (Tongyi Qianwen): `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Moonshot: `https://api.moonshot.cn/v1`

---

## Docker Related

### Q13: Docker container exits immediately after starting?

**Solution**:
1. View container logs:
   ```bash
   docker logs <container_id>
   ```
2. Common causes:
   - Environment variables not correctly configured
   - `.env` file format error (e.g., extra spaces)
   - Dependency package version conflicts

---

### Q14: API service inaccessible in Docker?

**Solution**:
1. Ensure startup command includes `--host 0.0.0.0` (cannot be 127.0.0.1)
2. Check port mapping is correct:
   ```yaml
    ports:
      - "8000:8000"
    ```

---

### Q14.1: Where is the software version stored when I install with Docker?

**Short answer**: For Docker users, the authoritative version is **the image tag you actually deployed**, not a hardcoded constant in a Python source file.

**Why**:
1. Docker publishing is driven by `.github/workflows/docker-publish.yml`, which only publishes release images for Git tags matching `v*.*.*` (for example, `v3.12.0`).
2. So the Docker image version follows the **GitHub Release / Git tag**, rather than a fixed value in `main.py`, `server.py`, or another backend module.
3. The `version` field in `apps/dsa-web/package.json` is currently a placeholder `0.0.0`. The WebUI version/build card is useful for checking whether frontend assets were rebuilt, but it is not the Docker release version.

**How to check your current Docker version**:
1. **Check the image tag in your deploy command or Compose file**. For example, in `ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0`, the deployed version is `v3.12.0`.
2. **If you used `latest`**, check your original `docker pull`, `docker-compose.yml`, or deployment script, then compare with [GitHub Releases](https://github.com/ZhuLinsen/daily_stock_analysis/releases).
3. **If you only want to confirm the frontend was refreshed**, open WebUI → Settings and inspect `Build ID` / `Build Time`; that confirms static asset freshness, not the Docker release version.

**Recommendation**: To avoid repeated updates, prefer a pinned version tag such as `v3.12.0` instead of relying on `latest`.

---


## Other Issues

### Q16: How to run only market review, without stock analysis?

**Method**:
```bash
# Local run
python main.py --market-only

# GitHub Actions
# Select mode: market-only when manually triggering
```

---

### Q17: Buy/Hold/Sell counts in analysis results are incorrect?

**Cause**: Earlier versions used regex matching for statistics, may not match actual recommendations.

**Solution**: Fixed in latest version, AI model now directly outputs `decision_type` field for accurate statistics.

---

## Still Have Questions?

If the above content doesn't solve your issue, welcome to:
1. Check [Complete Configuration Guide](full-guide_EN.md)
2. Search or submit [GitHub Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)
3. Check [Changelog](CHANGELOG.md) for latest fixes

---

*Last updated: 2026-08-03*
