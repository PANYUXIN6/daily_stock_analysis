import os
from unittest.mock import patch

import pytest

from src.config import Config, normalize_llm_channel_model
from src.services.system_config_service import SystemConfigService


def test_deepseek_keys_model_defaults_and_rotation():
    with patch('src.config.setup_env'), patch.dict(os.environ, {'DEEPSEEK_API_KEYS': 'key-first,key-second'}, clear=True):
        config = Config._load_from_env()
    assert config.litellm_model == 'deepseek/deepseek-flash'
    assert config.vision_model == 'deepseek/deepseek-flash'
    assert [item['litellm_params']['api_key'] for item in config.llm_model_list] == ['key-first', 'key-second']


@pytest.mark.parametrize('model', ['openai/gpt-5', 'anthropic/claude', 'gemini/gemini-pro', 'ollama/deepseek-r1'])
def test_foreign_models_are_rejected_at_config_boundary(model):
    with pytest.raises(ValueError, match='DeepSeek'):
        Config(litellm_model=model)
    issues = SystemConfigService._validate_llm_runtime_selection({'LITELLM_MODEL': model})
    assert issues[0]['code'] == 'unsupported_model'


def test_channel_cannot_forward_key_to_other_service():
    with pytest.raises(ValueError, match='DeepSeek'):
        normalize_llm_channel_model('deepseek-flash', 'deepseek', 'https://other.example/v1')


def test_yaml_allows_deepseek_alias_but_rejects_other_provider(tmp_path):
    route = tmp_path / 'models.yaml'
    route.write_text('model_list:\n  - model_name: analysis\n    litellm_params:\n      model: deepseek/deepseek-flash\n      api_key: test-key\n')
    deployments = Config._parse_litellm_yaml(str(route))
    assert Config(litellm_model='analysis', llm_model_list=deployments).litellm_model == 'analysis'
    route.write_text(route.read_text().replace('deepseek/deepseek-flash', 'openai/gpt-5'))
    assert Config._parse_litellm_yaml(str(route)) == []
