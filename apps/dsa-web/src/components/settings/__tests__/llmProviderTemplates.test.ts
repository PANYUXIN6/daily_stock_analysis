import { describe, expect, it } from 'vitest';
import { LLM_PROVIDER_TEMPLATES, MODEL_PLACEHOLDERS_BY_PROTOCOL, getProviderTemplate, isKnownProviderTemplate } from '../llmProviderTemplates';

describe('DeepSeek templates', () => {
  it('offers only the official DeepSeek API', () => {
    expect(LLM_PROVIDER_TEMPLATES.map((item) => item.channelId)).toEqual(['deepseek']);
    expect(getProviderTemplate('deepseek')?.baseUrl).toBe('https://api.deepseek.com');
    expect(MODEL_PLACEHOLDERS_BY_PROTOCOL).toEqual({ deepseek: 'deepseek-flash,deepseek-v4-pro' });
  });
  it('does not resolve unknown template identifiers', () => {
    expect(getProviderTemplate('unknown')).toBeUndefined();
    expect(isKnownProviderTemplate('unknown')).toBe(false);
    expect(getProviderTemplate('__proto__')).toBeUndefined();
  });
});
