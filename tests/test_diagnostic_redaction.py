"""Credential redaction remains shared by cloud-model error diagnostics."""
import json
import pytest
from src.core.config_registry import _FIELD_DEFINITIONS
from src.llm.diagnostic_redaction import redact_diagnostic_text
from src.llm import diagnostic_redaction as diagnostic_redaction_module

def _registered_sensitive_titles_needing_title_match() -> list[str]:
    titles = []
    for field_name, metadata in _FIELD_DEFINITIONS.items():
        if not isinstance(metadata, dict) or not metadata.get("is_sensitive"):
            continue
        title = metadata.get("title")
        if not isinstance(title, str) or not title:
            continue
        if title.upper() in {field_name.upper(), field_name.replace("_", " ").upper()}:
            continue
        titles.append(title)
    return sorted(set(titles))


def test_diagnostics_redaction_and_truncation() -> None:
    text = (
        "Authorization: Bearer sk-abc123456789012345678901234567890 "
        "https://user:pass@example.com/path "
        + "safe text " * 20
    )

    redacted = redact_diagnostic_text(text, home="/Users/example", limit=60)

    assert "sk-abc" not in redacted
    assert "user:pass" not in redacted
    assert "<truncated>" in redacted


def test_diagnostics_redacts_webhook_urls_and_preserves_adjacent_normal_urls() -> None:
    text = (
        "slack=https://hooks.slack.com/services/T000/B000/super-secret "
        "dingtalk=https://oapi.dingtalk.com/robot/send?access_token=abc123&foo=bar "
        "docs=https://example.com/public/docs?foo=bar"
    )

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "hooks.slack.com" not in redacted
    assert "oapi.dingtalk.com" not in redacted
    assert "super-secret" not in redacted
    assert "access_token" not in redacted
    assert redacted.count("<redacted-url>") == 2
    assert "https://example.com/public/docs?foo=bar" in redacted


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("FEISHU_APP_SECRET=xxy12345abcdef", "xxy12345abcdef"),
        ("AIHUBMIX_KEY=short", "short"),
        ("CUSTOM_API_KEY=abc123xyz789short", "abc123xyz789short"),
        ("TUSHARE_TOKEN=short", "short"),
        ("NTFY_URL=https://ntfy.sh/private-topic", "https://ntfy.sh/private-topic"),
        ("API_KEYS=short", "short"),
        ("OPENAI_API_KEYS=short", "short"),
        ("MYOPENAIKEY=short", "short"),
        ("OPENAI_V2_API_KEY=short", "short"),
        (r"OPENAI_FOO=\ tiny-secret session_id=ok", "tiny-secret"),
        ("OPENAI_API_KEY=\\\ntiny-secret session_id=ok", "tiny-secret"),
        ("OPENAI_FOO=$(printf %s tiny-secret) session_id=ok", "tiny-secret"),
        ("export OPENAI_FOO=$(printf %s tiny-secret) session_id=ok", "tiny-secret"),
        ("PUSHOVER_USER_KEY=short", "short"),
        ("R2_SECRET_ACCESS_KEY=short", "short"),
        ("My_Api_Key=myvalue", "myvalue"),
        ("API Key: tiny-secret session_id=ok", "tiny-secret"),
        ("Client Secret: tiny-secret session_id=ok", "tiny-secret"),
        ("Secret Access Key: tiny-secret session_id=ok", "tiny-secret"),
        ("DingTalk App Key: tiny-secret session_id=ok", "tiny-secret"),
        ("Pushover User Key: tiny-secret session_id=ok", "tiny-secret"),
        ('{"Database URL":"tiny-secret","session_id":"ok"}', "tiny-secret"),
        ("PASSWORD='abc def ghi' next", "abc def ghi"),
        ("SESSION_SECRET='abc def ghi' next", "abc def ghi"),
        ("Authorization: Bearer tiny", "tiny"),
        ('"api_key": "short123"', "short123"),
        ('{"accessToken":"short123"}', "short123"),
        ("api_keys: short123", "short123"),
        ("bot_token: tiny", "tiny"),
        ("telegram_bot_token: tiny", "tiny"),
        ("client_secret: tiny", "tiny"),
        ("clientSecret: tiny", "tiny"),
        ("database_url: sqlite-short", "sqlite-short"),
        ("aws_secret_access_key: tiny", "tiny"),
        ("db_passwd: tiny-secret", "tiny-secret"),
        ('{"db_passwd":"tiny-secret"}', "tiny-secret"),
        ('{"set-cookie":"session=tiny-secret"}', "tiny-secret"),
        (r'{"api\u005fkey":"tiny-secret"}', "tiny-secret"),
        (r'{"api\x5fkey":"tiny-secret"}', "tiny-secret"),
        ("OPENAI_API_KEY='x'\"'\"'tiny-secret' session_id=ok", "tiny-secret"),
        ("OPENAI_API_KEY+=tiny-secret session_id=ok", "tiny-secret"),
        ("{'api_key': 'tiny-secret', 'session_id': 'ok'}", "tiny-secret"),
        ("'password': tiny-secret session_id=ok", "tiny-secret"),
    ],
)
def test_diagnostics_redacts_short_credential_assignments(text: str, secret: str) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    assert secret not in redacted
    assert "<redacted>" in redacted


def test_diagnostics_redacts_yaml_scalars_with_spaces_and_blocks() -> None:
    text = (
        "retry: 3 password: correct horse battery staple\n"
        "backup_password: 'correct horse''s secret'\n"
        "INFO private_key: |\n"
        "  tiny-secret\n"
        "  second secret line\n"
        "token_budget: 1000\n"
    )

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "correct horse battery staple" not in redacted
    assert "correct horse''s secret" not in redacted
    assert "tiny-secret" not in redacted
    assert "second secret line" not in redacted
    assert "retry: 3" in redacted
    assert "token_budget: 1000" in redacted
    assert "password: <redacted>" in redacted
    assert "backup_password: '<redacted>'\n" in redacted
    assert "''s secret" not in redacted
    assert "private_key: <redacted>" in redacted


def test_diagnostics_redacts_yaml_block_scalars_with_node_properties() -> None:
    text = (
        "private_key: !<tag:yaml.org,2002:str> &pem |\n"
        "  tiny-secret\n"
        "session_id: yaml123\n"
    )

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "tiny-secret" not in redacted
    assert redacted == "private_key: <redacted>\nsession_id: yaml123\n"


def test_diagnostics_preserves_non_sensitive_spaced_key_labels() -> None:
    text = "Cache Key: shard-one\nSort Key: created-at\nsession_id: ok\n"

    assert redact_diagnostic_text(text, limit=1000) == text


@pytest.mark.parametrize(
    ("text", "secrets", "preserved"),
    [
        (
            "? api_key\n: tiny-secret\nsession_id: yaml123\n",
            ("tiny-secret",),
            "session_id: yaml123",
        ),
        (
            "? 'api_key'\n: single-quoted-secret\nsession_id: yaml123\n",
            ("single-quoted-secret",),
            "session_id: yaml123",
        ),
        (
            '? "api_key"\n: double-quoted-secret\nsession_id: yaml123\n',
            ("double-quoted-secret",),
            "session_id: yaml123",
        ),
        (
            '? "api\\x5fkey"\n: tiny-secret\nsession_id: yaml123\n',
            ("tiny-secret",),
            "session_id: yaml123",
        ),
        (
            "? credentials\n:\n- tiny-one\n- tiny-two\nsession_id: yaml123\n",
            ("tiny-one", "tiny-two"),
            "session_id: yaml123",
        ),
        (
            "? private_key\n: |\n  tiny-secret\nsession_id: yaml123\n",
            ("tiny-secret",),
            "session_id: yaml123",
        ),
        (
            "- ? api_key\n  : tiny-secret\nsession_id: yaml123\n",
            ("tiny-secret",),
            "session_id: yaml123",
        ),
        (
            "? !!str api_key\n: tiny-secret\nsession_id: yaml123\n",
            ("tiny-secret",),
            "session_id: yaml123",
        ),
        (
            "- ? &cred private_key\n  : tiny-secret\nsession_id: yaml123\n",
            ("tiny-secret",),
            "session_id: yaml123",
        ),
        (
            "- ? credentials\n  :\n  - tiny-one\n  - tiny-two\nsession_id: yaml123\n",
            ("tiny-one", "tiny-two"),
            "session_id: yaml123",
        ),
        (
            "? api_key\n# note\n: tiny-secret\nsession_id: yaml123\n",
            ("tiny-secret",),
            "session_id: yaml123",
        ),
        (
            "? api_key\n  # note\n: tiny-secret\nsession_id: yaml123\n",
            ("tiny-secret",),
            "session_id: yaml123",
        ),
        (
            "? api_key\n\n: tiny-secret\nsession_id: yaml123\n",
            ("tiny-secret",),
            "session_id: yaml123",
        ),
    ],
)
def test_diagnostics_redacts_yaml_explicit_sensitive_mappings(
    text: str,
    secrets: tuple[str, ...],
    preserved: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    for secret in secrets:
        assert secret not in redacted
    assert ": <redacted>" in redacted
    assert preserved in redacted


def test_diagnostics_redacts_indented_values_under_empty_sensitive_yaml_field() -> None:
    text = "api_keys:\n  - tiny-one\n  - tiny-two\nsession_id: yaml123\n"

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "tiny-one" not in redacted
    assert "tiny-two" not in redacted
    assert "api_keys: <redacted>\n" in redacted
    assert "session_id: yaml123\n" in redacted


def test_diagnostics_redacts_comment_only_sensitive_yaml_field_blocks() -> None:
    text = "api_keys: # configured keys\n  - tiny-one\n  - tiny-two\nsession_id: yaml123\n"

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "tiny-one" not in redacted
    assert "tiny-two" not in redacted
    assert "api_keys: <redacted>\n" in redacted
    assert "session_id: yaml123\n" in redacted


def test_diagnostics_redacts_comment_lines_within_sensitive_yaml_field_blocks() -> None:
    text = "api_keys: # configured keys\n# nested note\n- tiny-one\n- tiny-two\nsession_id: yaml123\n"

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "nested note" not in redacted
    assert "tiny-one" not in redacted
    assert "tiny-two" not in redacted
    assert redacted == "api_keys: <redacted>\nsession_id: yaml123\n"


def test_diagnostics_redacts_indentless_sequences_under_sensitive_yaml_field() -> None:
    text = "api_keys:\n- tiny-one\n- tiny-two\nsession_id: yaml123\n"

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "tiny-one" not in redacted
    assert "tiny-two" not in redacted
    assert "api_keys: <redacted>\n" in redacted
    assert "session_id: yaml123\n" in redacted


def test_diagnostics_redacts_sensitive_collections() -> None:
    text = (
        "api_keys: [first-secret, second-secret] token_budget: 1000\n"
        '{"credentials":{"username":"alice","value":"tiny-secret"},"session_id":"abc123"}'
    )

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "first-secret" not in redacted
    assert "second-secret" not in redacted
    assert "tiny-secret" not in redacted
    assert "api_keys: <redacted> token_budget: 1000" in redacted
    assert '{"credentials":<redacted>,"session_id":"abc123"}' in redacted


@pytest.mark.parametrize(
    ("text", "secret_values", "preserved"),
    [
        (
            "api_keys:\n  - tiny-one\n  - tiny-two\nsession_id: abc123\n",
            ("tiny-one", "tiny-two"),
            "session_id: abc123",
        ),
        (
            "credentials:\n  username: alice\n  value: tiny-secret\nsession_id: abc123\n",
            ("alice", "tiny-secret"),
            "session_id: abc123",
        ),
        (
            "private_key:\n  tiny-secret\nfoo: bar\n",
            ("tiny-secret",),
            "foo: bar",
        ),
        (
            "api_keys: # configured keys\n  - tiny-one\nsession_id: abc123\n",
            ("tiny-one",),
            "session_id: abc123",
        ),
        (
            "api_keys:\n- tiny-one\n- tiny-two\nsession_id: abc123\n",
            ("tiny-one", "tiny-two"),
            "session_id: abc123",
        ),
        (
            "private_key: &pem |\n  tiny-secret\nsession_id: abc123\n",
            ("tiny-secret",),
            "session_id: abc123",
        ),
        (
            "credentials: !vault &creds\n  value: tiny-secret\nsession_id: abc123\n",
            ("tiny-secret",),
            "session_id: abc123",
        ),
        (
            "cookie:\n  session: tiny-one\n  csrf: tiny-two\nsession_id: abc123\n",
            ("tiny-one", "tiny-two"),
            "session_id: abc123",
        ),
        (
            "password: correct horse\n  battery staple\nsession_id: abc123\n",
            ("correct horse", "battery staple"),
            "session_id: abc123",
        ),
        (
            '"password": correct horse\n battery staple\nsession_id: abc123\n',
            ("correct horse", "battery staple"),
            "session_id: abc123",
        ),
        (
            '"password":\n  tiny-one\n  tiny-two\nsession_id: abc123\n',
            ("tiny-one", "tiny-two"),
            "session_id: abc123",
        ),
        (
            'password: !secret "tiny-one\n  tiny-two"\nsession_id: abc123\n',
            ("tiny-one", "tiny-two"),
            "session_id: abc123",
        ),
        (
            "authorization:\n  scheme: Bearer\n  credentials: tiny-auth\nsession_id: abc123\n",
            ("Bearer", "tiny-auth"),
            "session_id: abc123",
        ),
        (
            "Authorization: Basic tiny-auth\n  continued-secret\nsession_id: abc123\n",
            ("tiny-auth", "continued-secret"),
            "session_id: abc123",
        ),
        (
            "API Key:\n  - tiny-one\n  - tiny-two\nsession_id: abc123\n",
            ("tiny-one", "tiny-two"),
            "session_id: abc123",
        ),
        (
            "'credentials':\n  username: alice\n  value: tiny-secret\nsession_id: abc123\n",
            ("alice", "tiny-secret"),
            "session_id: abc123",
        ),
    ],
)
def test_diagnostics_redacts_indented_blocks_under_empty_sensitive_yaml_fields(
    text: str,
    secret_values: tuple[str, ...],
    preserved: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    for secret in secret_values:
        assert secret not in redacted
    assert "<redacted>" in redacted
    assert preserved in redacted


@pytest.mark.parametrize(
    ("text", "secret", "preserved"),
    [
        (
            '{"AIHUBMIX_KEY":"json-short","session_id":"json123"}',
            "json-short",
            '"session_id":"json123"',
        ),
        (
            '{"DINGTALK_APP_KEY":"ding-short","session_id":"ding123"}',
            "ding-short",
            '"session_id":"ding123"',
        ),
        (
            "WECOM_ENCODING_AES_KEY: wecom-short\nsession_id: wecom123\n",
            "wecom-short",
            "session_id: wecom123",
        ),
        (
            "PUSHOVER_USER_KEY: push-short\nsession_id: push123\n",
            "push-short",
            "session_id: push123",
        ),
        (
            '{"NTFY_URL":"private-topic","session_id":"ntfy123"}',
            "private-topic",
            '"session_id":"ntfy123"',
        ),
    ],
)
def test_diagnostics_applies_registered_sensitive_names_to_structured_fields(
    text: str,
    secret: str,
    preserved: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    assert secret not in redacted
    assert "<redacted>" in redacted
    assert preserved in redacted


@pytest.mark.parametrize(
    "field_name",
    sorted(
        diagnostic_redaction_module._SENSITIVE_ENV_EXACT_NAMES
        | diagnostic_redaction_module._registered_sensitive_env_exact_names()
    ),
)
def test_all_registered_sensitive_exact_names_are_redacted_in_json(
    field_name: str,
) -> None:
    redacted = redact_diagnostic_text(
        json.dumps({field_name: "tinyZ9", "session_id": "json123"}),
        limit=1000,
    )

    assert "tinyZ9" not in redacted
    assert '"session_id": "json123"' in redacted


@pytest.mark.parametrize(
    "field_name",
    sorted(diagnostic_redaction_module._registered_sensitive_env_exact_names()),
)
def test_all_registered_sensitive_exact_names_are_redacted_as_spaced_labels(
    field_name: str,
) -> None:
    label = field_name.replace("_", " ")

    redacted = redact_diagnostic_text(
        f"{label}: tinyZ9 session_id=label123",
        limit=1000,
    )

    assert "tinyZ9" not in redacted
    assert "<redacted>" in redacted


@pytest.mark.parametrize(
    "field_title",
    _registered_sensitive_titles_needing_title_match(),
)
def test_registered_sensitive_config_titles_are_redacted_as_structured_labels(
    field_title: str,
) -> None:
    redacted = redact_diagnostic_text(
        f"{field_title}: tiny-secret session_id=label123",
        limit=1000,
    )

    assert "tiny-secret" not in redacted
    assert "<redacted>" in redacted
    assert "session_id=label123" in redacted


@pytest.mark.parametrize(
    "field_title",
    _registered_sensitive_titles_needing_title_match(),
)
def test_registered_sensitive_config_titles_are_redacted_in_json(
    field_title: str,
) -> None:
    redacted = redact_diagnostic_text(
        json.dumps({field_title: "tiny-secret", "session_id": "json123"}),
        limit=1000,
    )

    assert "tiny-secret" not in redacted
    assert "<redacted>" in redacted
    assert '"session_id": "json123"' in redacted


def test_diagnostics_redacts_ansi_prefixed_sensitive_fields() -> None:
    text = "\x1b[31mpassword: tiny\x1b[0m session_id=abc123 \x1b[32mapi_key: short123\x1b[0m"

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "\x1b[" not in redacted
    assert "tiny" not in redacted
    assert "short123" not in redacted
    assert redacted == "password: <redacted>"


@pytest.mark.parametrize(
    ("text", "secret", "preserved"),
    [
        (
            "Authorization: Basic dGlueTpzZWNyZXQ= session_id=abc123",
            "dGlueTpzZWNyZXQ=",
            "session_id=abc123",
        ),
        (
            "Authorization: Token tiny-secret token_budget=1000",
            "tiny-secret",
            "token_budget=1000",
        ),
        (
            "authorization=Negotiate abc.def.ghi token_budget=1000",
            "abc.def.ghi",
            "token_budget=1000",
        ),
        (
            'Authorization: Digest username="foo", realm="example", response="tiny-secret" session_id=abc123',
            "tiny-secret",
            "session_id=abc123",
        ),
        (
            "Proxy-Authorization: Basic tiny-secret session_id=abc123",
            "tiny-secret",
            "session_id=abc123",
        ),
        (
            "proxy-authorization=Negotiate abc.def.ghi token_budget=1000",
            "abc.def.ghi",
            "token_budget=1000",
        ),
        (
            "proxy_authorization: Basic underscore-secret session_id=proxy123",
            "underscore-secret",
            "session_id=proxy123",
        ),
        (
            "'authorization': Bearer tiny-secret session_id=ok",
            "tiny-secret",
            "session_id=ok",
        ),
        (
            "'proxy_authorization': Basic tiny-secret session_id=ok",
            "tiny-secret",
            "session_id=ok",
        ),
        (
            '"authorization": Bearer tiny-secret session_id=ok',
            "tiny-secret",
            "session_id=ok",
        ),
        (
            '"proxy_authorization": Basic tiny-secret session_id=ok',
            "tiny-secret",
            "session_id=ok",
        ),
        (
            "proxyAuthorization=Negotiate camel.secret token_budget=1000",
            "camel.secret",
            "token_budget=1000",
        ),
    ],
)
def test_diagnostics_redacts_non_bearer_authorization_values(
    text: str,
    secret: str,
    preserved: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    assert secret not in redacted
    assert preserved in redacted
    assert (
        "Authorization: <redacted>" in redacted
        or "authorization=<redacted>" in redacted
        or "Proxy-Authorization: <redacted>" in redacted
        or "proxy-authorization=<redacted>" in redacted
        or "proxy_authorization: <redacted>" in redacted
        or "'authorization': <redacted>" in redacted
        or "'proxy_authorization': <redacted>" in redacted
        or '"authorization": <redacted>' in redacted
        or '"proxy_authorization": <redacted>' in redacted
        or "proxyAuthorization=<redacted>" in redacted
    )


def test_diagnostics_redacts_parameterized_oauth_authorization_values() -> None:
    text = (
        'Authorization: OAuth oauth_consumer_key="client", '
        'oauth_signature="tiny-secret" session_id=abc123'
    )

    redacted = redact_diagnostic_text(text, limit=1000)

    assert "tiny-secret" not in redacted
    assert "Authorization: <redacted> session_id=abc123" in redacted


@pytest.mark.parametrize(
    ("text", "preserved"),
    [
        (
            "Authorization: Bearer first-secret Proxy-Authorization: Basic second-secret session_id=ok",
            "session_id=ok",
        ),
        (
            "Authorization: Bearer first-secret authorization=Basic second-secret session_id=ok",
            "session_id=ok",
        ),
    ],
)
def test_diagnostics_redacts_multiple_authorization_fields_on_one_line(
    text: str,
    preserved: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    assert "first-secret" not in redacted
    assert "second-secret" not in redacted
    assert preserved in redacted
    assert redacted.count("<redacted>") == 2


@pytest.mark.parametrize(
    ("text", "secret", "preserved"),
    [
        (
            "Authorization: AWS4-HMAC-SHA256 Credential=AKIA/test/aws4_request, "
            "SignedHeaders=host;x-amz-date, Signature=tiny-secret session_id=aws123",
            "tiny-secret",
            "session_id=aws123",
        ),
        (
            'Authorization: Signature keyId="client",algorithm="hmac-sha256",signature="tiny-secret" '
            "token_budget=1000",
            "tiny-secret",
            "token_budget=1000",
        ),
    ],
)
def test_diagnostics_redacts_parameterized_authorization_values_for_any_scheme(
    text: str,
    secret: str,
    preserved: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    assert secret not in redacted
    assert preserved in redacted
    assert "Authorization: <redacted>" in redacted


def test_diagnostics_redacts_unclosed_quoted_sensitive_scalar() -> None:
    redacted = redact_diagnostic_text('password: "correct horse battery staple', limit=1000)

    assert "correct horse battery staple" not in redacted
    assert redacted == "password: <redacted>"


def test_diagnostics_redacts_multiline_quoted_sensitive_scalar() -> None:
    redacted = redact_diagnostic_text(
        'password: "correct horse\n battery staple"\nsession_id=abc123\n',
        limit=1000,
    )

    assert "correct horse" not in redacted
    assert "battery staple" not in redacted
    assert redacted == "password: <redacted>\nsession_id=abc123\n"


def test_diagnostics_redacts_multiline_plain_scalar_under_double_quoted_yaml_key() -> None:
    redacted = redact_diagnostic_text(
        '"password": correct horse\n battery staple\nsession_id: abc123\n',
        limit=1000,
    )

    assert "correct horse" not in redacted
    assert "battery staple" not in redacted
    assert redacted == '"password": <redacted>\nsession_id: abc123\n'


def test_diagnostics_redacts_single_line_multiword_plain_scalar_under_double_quoted_yaml_key() -> None:
    redacted = redact_diagnostic_text(
        '"password": correct horse battery staple\nsession_id: abc123\n',
        limit=1000,
    )

    assert "correct horse" not in redacted
    assert "battery staple" not in redacted
    assert redacted == '"password": <redacted>\nsession_id: abc123\n'


def test_diagnostics_redacts_tagged_plain_scalar_under_double_quoted_yaml_key() -> None:
    redacted = redact_diagnostic_text(
        '!!str "password": correct horse battery staple\nsession_id: ok\n',
        limit=1000,
    )

    assert "correct horse" not in redacted
    assert "battery staple" not in redacted
    assert redacted == '!!str "password": <redacted>\nsession_id: ok\n'


def test_diagnostics_redacts_anchored_continued_plain_scalar_under_double_quoted_yaml_key() -> None:
    redacted = redact_diagnostic_text(
        '&pem "password": correct horse\n battery staple\nsession_id: ok\n',
        limit=1000,
    )

    assert "correct horse" not in redacted
    assert "battery staple" not in redacted
    assert redacted == '&pem "password": <redacted>\nsession_id: ok\n'


def test_diagnostics_redacts_tagged_uri_plain_scalar_under_double_quoted_yaml_key() -> None:
    redacted = redact_diagnostic_text(
        '!<tag:yaml.org,2002:str> "password": correct horse battery staple\nsession_id: ok\n',
        limit=1000,
    )

    assert "correct horse" not in redacted
    assert "battery staple" not in redacted
    assert redacted == '!<tag:yaml.org,2002:str> "password": <redacted>\nsession_id: ok\n'


def test_diagnostics_redacts_tagged_uri_continued_plain_scalar_under_double_quoted_yaml_key() -> None:
    redacted = redact_diagnostic_text(
        '!<tag:yaml.org,2002:str> "password": correct horse\n battery staple\nsession_id: ok\n',
        limit=1000,
    )

    assert "correct horse" not in redacted
    assert "battery staple" not in redacted
    assert redacted == '!<tag:yaml.org,2002:str> "password": <redacted>\nsession_id: ok\n'


def test_diagnostics_redacts_indentless_sequence_under_double_quoted_yaml_key() -> None:
    redacted = redact_diagnostic_text(
        '"password": # configured\n- tiny-one\n- tiny-two\nsession_id: abc123\n',
        limit=1000,
    )

    assert "configured" not in redacted
    assert "tiny-one" not in redacted
    assert "tiny-two" not in redacted
    assert redacted == '"password": <redacted>\nsession_id: abc123\n'


def test_diagnostics_redacts_pretty_printed_json_value_on_following_line() -> None:
    redacted = redact_diagnostic_text(
        '{\n  "api_key":\n    "tiny-secret",\n  "session_id": "json123"\n}',
        limit=1000,
    )

    assert "tiny-secret" not in redacted
    assert '"api_key":\n    "<redacted>"' in redacted
    assert '"session_id": "json123"' in redacted


@pytest.mark.parametrize(
    "text",
    [
        '{"authorization":"Bearer tiny-secret","session_id":"abc123"}',
        '{"cookie":"session=tiny-secret","session_id":"abc123"}',
    ],
)
def test_diagnostics_redacts_quoted_json_authentication_fields(text: str) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    assert "tiny-secret" not in redacted
    assert '"<redacted>"' in redacted
    assert '"session_id":"abc123"' in redacted


def test_diagnostics_preserves_json_structure_for_quoted_authorization_fields() -> None:
    redacted = redact_diagnostic_text(
        '{"authorization":"Bearer tiny-secret","session_id":"abc123"}',
        limit=1000,
    )

    assert redacted == '{"authorization":"<redacted>","session_id":"abc123"}'


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            '{"password": correct horse battery staple, "session_id": "ok"}',
            '{"password": <redacted>, "session_id": "ok"}',
        ),
        (
            '{"api_key": correct horse, "session_id": "ok"}',
            '{"api_key": <redacted>, "session_id": "ok"}',
        ),
        (
            "{'password': correct horse battery staple, 'session_id': 'ok'}",
            "{'password': <redacted>, 'session_id': 'ok'}",
        ),
        (
            "{password: correct horse, session_id: ok}",
            "{password: <redacted>, session_id: ok}",
        ),
    ],
)
def test_diagnostics_redacts_flow_style_sensitive_keys_with_unquoted_multiword_scalars(
    text: str,
    expected: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    assert "correct horse" not in redacted
    assert "battery staple" not in redacted
    assert redacted == expected


@pytest.mark.parametrize(
    "text",
    [
        "password: correct horse=staple session_id=abc123",
        "password: correct horse_staple=value session_id=abc123",
    ],
)
def test_diagnostics_fails_closed_for_unquoted_yaml_secret_with_assignment(
    text: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)
    assert redacted == "password: <redacted>"


@pytest.mark.parametrize(
    ("text", "secret", "expected"),
    [
        ("password: abc,def session_id=abc123", "abc,def", "password: <redacted>"),
        (
            "bot_token=tiny]} token_budget: 1000",
            "tiny]}",
            "bot_token=<redacted> token_budget: 1000",
        ),
    ],
)
def test_diagnostics_redacts_sensitive_scalars_with_punctuation(
    text: str,
    secret: str,
    expected: str,
) -> None:
    redacted = redact_diagnostic_text(text, limit=1000)

    assert secret not in redacted
    assert redacted == expected


@pytest.mark.parametrize(
    "text",
    [
        "MONKEY=banana next",
        "KEYBOARD_LAYOUT=us next",
        "retry: 3 token_budget: 1000",
        "docs=https://example.com/public/docs?monkey=banana&foo=bar",
        "analysis_key_factor=valuation next",
        "sort_key=price primary_key=id cache_key=reports",
        "session_id=abc123 user_session: abc123",
        'message: "normal diagnostic value"',
    ],
)
def test_diagnostics_preserves_noncredential_assignments(text: str) -> None:
    assert redact_diagnostic_text(text, limit=1000) == text
