# DeepSeek configuration

Only the official DeepSeek cloud API is supported for analysis, Agent chat, and image import.

```dotenv
DEEPSEEK_API_KEY=your-key
LITELLM_MODEL=deepseek/deepseek-flash
VISION_MODEL=deepseek/deepseek-flash
```

`DEEPSEEK_API_KEYS` accepts comma-separated keys and takes precedence over the single key. `AGENT_LITELLM_MODEL` inherits the primary model when blank. `LITELLM_FALLBACK_MODELS` accepts other DeepSeek models, such as `deepseek/deepseek-v4-pro`. Use `LLM_TEMPERATURE` and `LLM_REQUEST_DELAY` for temperature and request pacing.

Flash supports image input. Check the [official model documentation](https://api-docs.deepseek.com/quick_start/pricing/) for current availability.

Web settings support DeepSeek channels, connection tests, and JSON/tool/stream/vision probes. The only endpoint is `https://api.deepseek.com` (optional `/v1`), with the `deepseek` protocol and Chat Completions.

Advanced routing precedence: `LITELLM_CONFIG` YAML → `LLM_CHANNELS` → DeepSeek environment keys. YAML aliases are allowed; deployed models must use `deepseek/<model>` and the official endpoint. See [the YAML example](examples/litellm_config.example.yaml).

Remove obsolete provider settings and configure DeepSeek credentials. Replace the old request delay setting with `LLM_REQUEST_DELAY`. Existing reports and conversation records are retained. Connection tests may incur API charges.

### LLM usage HMAC telemetry

P0a usage telemetry creates HMAC-SHA256 fingerprints for the actual messages sent to the model. This only writes local `llm_usage` telemetry. It does not change prompts, provider parameters, cache hints, model output, or fallback order.

Usage is read in three tiers:

- Prefer the provider / LiteLLM public `usage` response field.
- Then read the LiteLLM public `usage_metadata` response field.
- Only then read `_hidden_params["usage"]`, which is a LiteLLM private/internal best-effort fallback rather than a stable public contract. If it is absent, usage/cache telemetry may be incomplete; the model request itself has not failed for that reason.

Cache-token normalization is allowlisted best-effort normalization only. The external field evidence and runtime boundaries are separated below so provider contracts, current LiteLLM normalization behavior, and repository-specific compatibility allowlists are not treated as the same thing:

| Provider / source | Fields read | Evidence and boundary | Coverage |
| --- | --- | --- | --- |
| DeepSeek | `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | DeepSeek Chat Completion docs state that `prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`: <https://api-docs.deepseek.com/api/create-chat-completion> | Covered by unit/mock tests; live API calls were not run for this cleanup |
| LiteLLM public response shape | `usage` / `usage_metadata` | Consumed according to the response / `Usage` object shape in the current dependency window `litellm>=1.80.10,!=1.82.7,!=1.82.8,<1.99.0`; this is not a LiteLLM 2.x compatibility guarantee | Covered by Analyzer / Agent / usage tests |
| LiteLLM private fallback | `_hidden_params["usage"]` | Private/internal best-effort fallback, not a stable LiteLLM public contract. It only fills narrow streaming telemetry gaps such as public zero-only/no-signal usage and does not change provider request parameters | Covered by unit/mock tests; absence only affects telemetry completeness, not model request success |

```env
LLM_USAGE_HMAC_SECRET=
LLM_USAGE_HMAC_KEY_VERSION=local-v1
```

- When `LLM_USAGE_HMAC_SECRET` is empty, the backend creates `.llm_usage_hmac_secret` in the data directory for local deployment-scoped comparisons.
- Set the same high-entropy random secret only when multiple deployments intentionally need comparable HMACs; generate one with `openssl rand -hex 32`.
- `.llm_usage_hmac_secret` is a local secret artifact and is ignored by filename in `.gitignore`.
- When rotating the secret, update `LLM_USAGE_HMAC_KEY_VERSION` so old and new fingerprints are not compared as if they used the same key.
- Do not reuse the login session secret and do not commit or expose the real secret in version control, issues, logs, or screenshots.

## Usage statistics

The usage page includes DeepSeek only across totals, call types, model groups, and recent calls. Recorded provider identity takes precedence; older rows without a provider are included only for `deepseek`, `deepseek/...`, or bare `deepseek-*` models. Other vendors’ historical rows remain stored but are excluded from statistics and display.
