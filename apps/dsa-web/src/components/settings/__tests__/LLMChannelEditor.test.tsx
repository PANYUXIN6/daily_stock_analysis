import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LLMChannelEditor } from '../LLMChannelEditor';

const {
  update,
  testLLMChannel,
  discoverLLMChannelModels,
} = vi.hoisted(() => ({
  update: vi.fn(),
  testLLMChannel: vi.fn(),
  discoverLLMChannelModels: vi.fn(),
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    update: (...args: unknown[]) => update(...args),
    testLLMChannel: (...args: unknown[]) => testLLMChannel(...args),
    discoverLLMChannelModels: (...args: unknown[]) => discoverLLMChannelModels(...args),
  },
}));

describe('LLMChannelEditor', () => {
  beforeEach(() => {
    update.mockReset();
    testLLMChannel.mockReset();
    discoverLLMChannelModels.mockReset();
  });

  const deepseekItems = [
    { key: 'LLM_CHANNELS', value: 'deepseek' },
    { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
    { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
    { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
    { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' },
    { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' },
    { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-flash' },
  ];

  function lastDraftCall(onDraftItemsChange: ReturnType<typeof vi.fn>) {
    const calls = onDraftItemsChange.mock.calls;
    return calls[calls.length - 1]?.[0] || [];
  }

  it('reports an empty generation backend draft when channel settings are unchanged', async () => {
    const onDraftItemsChange = vi.fn();
    const { rerender } = render(
      <LLMChannelEditor
        items={deepseekItems}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    await waitFor(() => expect(onDraftItemsChange).toHaveBeenCalledWith([]));
    expect(onDraftItemsChange).toHaveBeenCalledTimes(1);

    rerender(
      <LLMChannelEditor
        items={deepseekItems}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    expect(onDraftItemsChange).toHaveBeenCalledTimes(1);
  });

  it('reports unsaved channel edits as generation backend draft items', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={deepseekItems}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(await screen.findByLabelText('Base URL'), {
      target: { value: 'https://proxy.example.com/v1' },
    });
    fireEvent.change(screen.getByLabelText('API Key'), {
      target: { value: 'sk-draft' },
    });
    fireEvent.change(screen.getByLabelText('模型（逗号分隔）'), {
      target: { value: 'deepseek-flash,deepseek-v4-pro' },
    });

    await waitFor(() => {
      const draft = lastDraftCall(onDraftItemsChange);
      expect(draft).toContainEqual({ key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://proxy.example.com/v1' });
      expect(draft).toContainEqual({ key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-draft' });
      expect(draft).toContainEqual({ key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash,deepseek-v4-pro' });
    });
  });

  it('preserves an invalid saved API surface during an unrelated save', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_BASE_URL'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          ...deepseekItems,
          { key: 'LLM_DEEPSEEK_API_SURFACE', value: 'respones' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek/i }));
    expect(await screen.findByLabelText('API Surface')).toHaveValue('respones');
    expect(screen.getByRole('option', { name: '无效配置：respones' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://proxy.example.com/v1' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => expect(update).toHaveBeenCalled());
    const updateItemMap = new Map(
      update.mock.calls[0][0].items.map((item: { key: string; value: string }) => [item.key, item.value]),
    );
    expect(updateItemMap.get('LLM_DEEPSEEK_API_SURFACE')).toBe('respones');
  });

  it('returns to an empty generation backend draft after channel edits are restored', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={deepseekItems}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    const baseUrlInput = await screen.findByLabelText('Base URL');
    fireEvent.change(baseUrlInput, { target: { value: 'https://proxy.example.com/v1' } });
    await waitFor(() => expect(lastDraftCall(onDraftItemsChange)).toContainEqual({
      key: 'LLM_DEEPSEEK_BASE_URL',
      value: 'https://proxy.example.com/v1',
    }));

    fireEvent.change(baseUrlInput, { target: { value: 'https://api.deepseek.com' } });

    await waitFor(() => {
      expect(lastDraftCall(onDraftItemsChange)).toEqual([]);
    });
  });

  it('does not emit invalid channel env keys while the channel name is empty', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={deepseekItems}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(await screen.findByLabelText('渠道名称'), { target: { value: '' } });

    await waitFor(() => {
      expect(lastDraftCall(onDraftItemsChange)).toEqual([]);
    });
    expect(onDraftItemsChange.mock.calls.flatMap((call) => call[0]).some((item) => item.key.startsWith('LLM__'))).toBe(false);
  });

  it('renders API Key input with controlled visibility', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));

    const input = await screen.findByLabelText('API Key');
    expect(input).toHaveAttribute('type', 'password');

    fireEvent.click(screen.getByRole('button', { name: '显示内容' }));
    expect(input).toHaveAttribute('type', 'text');
  });

  it('shows help dialogs for channel editor fields', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(await screen.findByRole('button', { name: '查看 Base URL 配置说明' }));

    expect(screen.getByRole('dialog', { name: 'Base URL' })).toBeInTheDocument();
    expect(screen.getByText('该渠道的接口根地址。')).toBeInTheDocument();
    expect(screen.getByText('LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(await screen.findByRole('button', { name: '查看 Temperature 配置说明' }));

    expect(screen.getByRole('dialog', { name: 'Temperature' })).toBeInTheDocument();
    expect(screen.getByText('运行时统一采样温度。')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(await screen.findByRole('button', { name: '查看 运行时能力检测 配置说明' }));

    expect(screen.getByRole('dialog', { name: '运行时能力检测' })).toBeInTheDocument();
    expect(screen.getByText('选择能力后点击检测；检测会发起真实 LLM 请求。')).toBeInTheDocument();
  });

  it('hides LiteLLM wording when advanced YAML routing is enabled', () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LITELLM_CONFIG', value: './litellm_config.yaml' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    expect(screen.getByText(/检测到已配置高级模型路由 YAML/i)).toBeInTheDocument();
    expect(screen.getByText(/运行时主模型 \/ 备选模型 \/ Vision \/ Temperature 仍由下方通用字段决定/i)).toBeInTheDocument();
    expect(screen.queryByText(/LiteLLM/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/LITELLM_CONFIG/i)).not.toBeInTheDocument();
  });

  it('uses DeepSeek V4 defaults when adding the official preset', async () => {
    render(
      <LLMChannelEditor
        items={[]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'deepseek' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 添加渠道' }));

    await screen.findByRole('button', { name: /DeepSeek 官方/i });
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://api.deepseek.com');
    expect(screen.getByLabelText('模型（逗号分隔）')).toHaveValue('deepseek-flash,deepseek-v4-pro');
  });

  it('does not show provider metadata for custom or unknown channels', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy' },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1' },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true' },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-test' },
          { key: 'LLM_MY_PROXY_MODELS', value: 'custom-model' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));

    expect(screen.queryByText('配置参考')).not.toBeInTheDocument();
    expect(screen.queryByText(/官方来源/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/能力标签仅用于配置参考/i)).not.toBeInTheDocument();
  });

  it('only persists edited values for runtime-only channel keys', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_CHANNELS', 'LLM_MY_PROXY_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy', rawValueExists: false },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-v4-pro', rawValueExists: false },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'deepseek', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEYS', value: 'sk-runtime-only', rawValueExists: false },
          { key: 'LLM_MY_PROXY_MODELS', value: 'deepseek-flash', rawValueExists: false },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    fireEvent.change(screen.getByLabelText('模型（逗号分隔）'), { target: { value: 'deepseek-flash,deepseek-v4-pro' } });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    const updateItemMap = new Map(updatePayload.items.map((item: { key: string; value: string }) => [item.key, item.value]));

    expect(updateItemMap.get('LLM_MY_PROXY_MODELS')).toBe('deepseek-flash,deepseek-v4-pro');
    expect(updateItemMap.has('LITELLM_MODEL')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY_PROTOCOL')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY_BASE_URL')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY_API_KEY')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY_API_KEYS')).toBe(false);
  });

  it('renames a mixed raw/runtime channel and clears persisted API key field', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_MY_PROXY_API_KEY', 'LLM_MY_PROXY2_API_KEY', 'LLM_MY_PROXY2_BASE_URL', 'LLM_MY_PROXY2_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy' },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'deepseek', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-saved' },
          { key: 'LLM_MY_PROXY_MODELS', value: 'deepseek-flash', rawValueExists: false },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    fireEvent.change(screen.getByLabelText('渠道名称'), { target: { value: 'my_proxy2' } });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    const updateItemMap = new Map(updatePayload.items.map((item: { key: string; value: string }) => [item.key, item.value]));

    expect(updateItemMap.get('LLM_MY_PROXY_API_KEY')).toBe('');
    expect(updateItemMap.has('LLM_MY_PROXY_API_KEYS')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY_PROTOCOL')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY_BASE_URL')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY_MODELS')).toBe(false);
    expect(updateItemMap.get('LLM_MY_PROXY2_API_KEY')).toBe('sk-saved');
    expect(updateItemMap.get('LLM_MY_PROXY2_BASE_URL')).toBe('https://proxy.example.com/v1');
    expect(updateItemMap.get('LLM_MY_PROXY2_MODELS')).toBe('deepseek-flash');
  });

  it('uses runtime API_KEYS when both API_KEY and API_KEYS coexist', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy', rawValueExists: false },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'deepseek', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-saved' },
          { key: 'LLM_MY_PROXY_API_KEYS', value: 'sk-runtime-only', rawValueExists: false },
          { key: 'LLM_MY_PROXY_MODELS', value: 'deepseek-flash', rawValueExists: false },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    expect(screen.getByLabelText('API Key')).toHaveValue('sk-runtime-only');
  });

  it('does not migrate conflicted API key data as API_KEY when renaming a channel', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_CHANNELS', 'LLM_MY_PROXY_API_KEY', 'LLM_MY_PROXY2_PROTOCOL', 'LLM_MY_PROXY2_BASE_URL', 'LLM_MY_PROXY2_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy', rawValueExists: false },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'deepseek', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-saved' },
          { key: 'LLM_MY_PROXY_API_KEYS', value: 'sk-runtime-only', rawValueExists: false },
          { key: 'LLM_MY_PROXY_MODELS', value: 'deepseek-flash', rawValueExists: false },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    fireEvent.change(screen.getByLabelText('渠道名称'), { target: { value: 'my_proxy2' } });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    const updateItemMap = new Map(updatePayload.items.map((item: { key: string; value: string }) => [item.key, item.value]));

    expect(updateItemMap.get('LLM_CHANNELS')).toBe('my_proxy2');
    expect(updateItemMap.has('LLM_MY_PROXY2_API_KEY')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY2_API_KEYS')).toBe(false);
    expect([...updateItemMap.values()]).not.toContain('sk-runtime-only');
    expect([...updateItemMap.values()]).not.toContain('sk-saved');
    expect(updateItemMap.get('LLM_MY_PROXY_API_KEY')).toBe('');
    expect(updateItemMap.get('LLM_MY_PROXY2_BASE_URL')).toBe('https://proxy.example.com/v1');
    expect(updateItemMap.get('LLM_MY_PROXY2_MODELS')).toBe('deepseek-flash');
  });

  it('does not migrate runtime-only API keys when renaming a startup-env channel', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_CHANNELS', 'LLM_MY_PROXY2_BASE_URL', 'LLM_MY_PROXY2_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy', rawValueExists: false },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'deepseek', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEYS', value: 'sk-runtime-only', rawValueExists: false },
          { key: 'LLM_MY_PROXY_MODELS', value: 'deepseek-flash', rawValueExists: false },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    fireEvent.change(screen.getByLabelText('渠道名称'), { target: { value: 'my_proxy2' } });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    const updateItemMap = new Map(updatePayload.items.map((item: { key: string; value: string }) => [item.key, item.value]));

    expect(updateItemMap.get('LLM_CHANNELS')).toBe('my_proxy2');
    expect(updateItemMap.has('LLM_MY_PROXY_API_KEY')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY_API_KEYS')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY2_API_KEY')).toBe(false);
    expect(updateItemMap.has('LLM_MY_PROXY2_API_KEYS')).toBe(false);
    expect([...updateItemMap.values()]).not.toContain('sk-runtime-only');
  });

  it('sanitizes stale runtime models before saving DeepSeek V4 channel changes', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS', 'LITELLM_MODEL'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro,deepseek/deepseek-chat,cohere/command-r-plus' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('模型（逗号分隔）'), {
      target: { value: 'deepseek-flash,deepseek-v4-pro' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_MODEL', value: '' }),
        expect.objectContaining({ key: 'AGENT_LITELLM_MODEL', value: '' }),
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' }),
        expect.objectContaining({ key: 'VISION_MODEL', value: '' }),
        expect.objectContaining({ key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash,deepseek-v4-pro' }),
      ]),
    );
  });

  it('prompts when bare runtime models loosely match canonical OpenAI route aliases', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_PRIMARY_BASE_URL', 'LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'primary' },
          { key: 'LLM_PRIMARY_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_PRIMARY_BASE_URL', value: 'https://api.example.com/v1' },
          { key: 'LLM_PRIMARY_ENABLED', value: 'true' },
          { key: 'LLM_PRIMARY_API_KEY', value: 'sk-test' },
          { key: 'LLM_PRIMARY_MODELS', value: 'deepseek-flash' },
          { key: 'LITELLM_MODEL', value: 'deepseek-flash' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek-flash' },
          { key: 'AGENT_LITELLM_MODEL', value: '' },
          { key: 'VISION_MODEL', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /primary/i }));
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.example.com/compatible/v1' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(screen.getByText('当前运行时模型使用非规范 route alias，请从下拉框重新选择规范模型。')).toBeInTheDocument();
    });

    expect(update).not.toHaveBeenCalled();
  });

  it('sanitizes stale runtime models when enabled channels have no available models', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_BASE_URL', 'LITELLM_MODEL', 'AGENT_LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS', 'VISION_MODEL'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'false' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-v4-pro' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-chat' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.deepseek.com/v1' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_MODEL', value: '' }),
        expect.objectContaining({ key: 'AGENT_LITELLM_MODEL', value: '' }),
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: '' }),
        expect.objectContaining({ key: 'VISION_MODEL', value: '' }),
      ]),
    );
  });

  it('keeps legacy-key-backed runtime models when enabled channels have no available models', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_PRIMARY_BASE_URL', 'LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'primary' },
          { key: 'LLM_PRIMARY_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_PRIMARY_BASE_URL', value: 'https://api.example.com/v1' },
          { key: 'LLM_PRIMARY_ENABLED', value: 'false' },
          { key: 'LLM_PRIMARY_API_KEY', value: 'sk-test' },
          { key: 'LLM_PRIMARY_MODELS', value: 'deepseek-flash' },
          { key: 'DEEPSEEK_API_KEY', value: 'sk-legacy-value' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-flash' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' },
          { key: 'AGENT_LITELLM_MODEL', value: '' },
          { key: 'VISION_MODEL', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /primary/i }));
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.example.com/compatible/v1' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_MODEL', value: 'deepseek/deepseek-flash' }),
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' }),
      ]),
    );
  });

  it('shows cleanup warning and restore path after stale runtime models are removed on save', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS', 'LITELLM_MODEL'],
      warnings: [
        '检测到已同步清理失效的运行时模型引用：主模型 / Agent 主模型 / Vision 模型 / 备选模型中的失效项。如需恢复，请先补回对应渠道模型列表后重新选择；也可用Web 导出备份或手动 .env 还原之前的 LLM_* / LITELLM_MODEL / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE。',
      ],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro,deepseek/deepseek-chat' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('模型（逗号分隔）'), {
      target: { value: 'deepseek-flash,deepseek-v4-pro' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    expect(await screen.findByText('保存后提示')).toBeInTheDocument();
    expect(screen.getByText(/已同步清理失效的运行时模型引用/i)).toBeInTheDocument();
    expect(screen.getByText(/Web 导出备份或手动 \.env 还原/i)).toBeInTheDocument();
  });

  it('keeps save warnings visible after onSaved-driven refresh', async () => {
    const warningMessage = '检测到已同步清理失效的运行时模型引用：主模型 / Agent 主模型 / Vision 模型 / 备选模型中的失效项。';
    const initialItems = [
      { key: 'LLM_CHANNELS', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
      { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
      { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
      { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner' },
      { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
      { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
      { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' },
      { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
    ];
    const Component = () => {
      const [items, setItems] = useState(initialItems);

      return (
        <LLMChannelEditor
          items={items}
          configVersion="v1"
          maskToken="******"
          onSaved={async (updatedItems) => {
            setItems(updatedItems);
          }}
        />
      );
    };

    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS', 'LITELLM_MODEL'],
      warnings: [warningMessage],
    });

    render(<Component />);

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('模型（逗号分隔）'), {
      target: { value: 'deepseek-flash,deepseek-v4-pro' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    expect(await screen.findByText('保存后提示')).toBeInTheDocument();
    expect(screen.getByText(warningMessage)).toBeInTheDocument();
  });

  it('clears failed-save feedback after saved props refresh', async () => {
    const initialItems = [
      { key: 'LLM_CHANNELS', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
      { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
      { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' },
      { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' },
    ];
    const onSaved = vi.fn(async () => {
      throw new Error('refresh failed');
    });

    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_BASE_URL'],
      warnings: [],
    });

    const renderResult = render(
      <LLMChannelEditor
        items={initialItems}
        configVersion="v1"
        maskToken="******"
        onSaved={onSaved}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.deepseek.com/test' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    expect(await screen.findByText('refresh failed')).toBeInTheDocument();

    const savedItems = update.mock.calls[0][0].items;
    renderResult.rerender(
      <LLMChannelEditor
        items={savedItems}
        configVersion="v2"
        maskToken="******"
        onSaved={onSaved}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByText('refresh failed')).not.toBeInTheDocument();
    });
  });

  it('keeps stale runtime fallback model available when user restores it in channel models', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS', 'LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: '' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-old' },
          { key: 'VISION_MODEL', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('模型（逗号分隔）'), {
      target: { value: 'deepseek-chat,deepseek-old' },
    });

    expect(await screen.findByLabelText('deepseek/deepseek-old')).toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));
    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-old' }),
      ]),
    );
  });

  it('keeps runtime selections while channel models are edited temporarily', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner,deepseek-v4-pro' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    const primaryModelSelect = screen.getByRole('combobox', { name: '主模型' });
    const agentModelSelect = screen.getByRole('combobox', { name: 'Agent 主模型' });
    const visionModelSelect = screen.getByRole('combobox', { name: 'Vision 模型' });

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    const modelInput = screen.getByLabelText('模型（逗号分隔）');
    fireEvent.change(modelInput, {
      target: { value: 'deepseek-flash' },
    });

    await waitFor(() => {
      expect(primaryModelSelect).toHaveValue('deepseek/deepseek-chat');
      expect(agentModelSelect).toHaveValue('deepseek/deepseek-reasoner');
      expect(visionModelSelect).toHaveValue('deepseek/deepseek-reasoner');
    });

    fireEvent.change(modelInput, {
      target: { value: 'deepseek-chat,deepseek-reasoner,deepseek-v4-pro' },
    });

    await waitFor(() => {
      expect(primaryModelSelect).toHaveValue('deepseek/deepseek-chat');
      expect(agentModelSelect).toHaveValue('deepseek/deepseek-reasoner');
      expect(visionModelSelect).toHaveValue('deepseek/deepseek-reasoner');
      expect(screen.getByLabelText('deepseek/deepseek-v4-pro')).toBeChecked();
    });
  });

  it('checks protocol-prefixed selected model when discovery returns bare id', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'deepseek',
      models: ['MiniMax-M1'],
      latencyMs: 80,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek/MiniMax-M1' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const checkbox = await screen.findByLabelText('MiniMax-M1');
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    await waitFor(() => {
      expect(screen.getByLabelText('手动模型（逗号分隔）')).toHaveValue('');
    });
  });

  it('discovers models and writes selected values back to channel config', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'deepseek',
      models: ['deepseek-flash', 'qwen-turbo'],
      latencyMs: 88,
    });
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'qwen-old' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const qwenPlusCheckbox = await screen.findByLabelText('deepseek-flash');
    fireEvent.click(qwenPlusCheckbox);

    await waitFor(() => {
      expect(screen.getByLabelText('手动模型（逗号分隔）')).toHaveValue('qwen-old,deepseek-flash');
    });

    expect(discoverLLMChannelModels).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'deepseek',
        protocol: 'deepseek',
        baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        apiKey: 'sk-test',
        models: ['qwen-old'],
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: '保存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LLM_DEEPSEEK_MODELS', value: 'qwen-old,deepseek-flash' }),
      ]),
    );
  });

  it('shows structured troubleshooting hint when channel auth fails', async () => {
    testLLMChannel.mockResolvedValue({ success: false, message: 'LLM authentication failed', error: '401 Unauthorized · Bearer [REDACTED]', errorCode: 'auth', stage: 'chat_completion', retryable: false, details: {}, resolvedProtocol: 'deepseek', resolvedModel: 'deepseek/deepseek-flash', latencyMs: null });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' }, { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' }, { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' }, { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/聊天调用 · 鉴权失败：LLM authentication failed/i)).toBeInTheDocument();
    expect(screen.getByText(/请检查 API Key 是否正确/i)).toBeInTheDocument();
    expect(screen.queryByText(/调整模型顺序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('shows tested model and model-availability hints when a model is disabled', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM channel test failed',
      error: 'litellm.APIError: APIError: OpenAIException - Model disabled.',
      errorCode: 'model_not_found',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'model_access_denied', model: 'deepseek/deepseek-flash' },
      resolvedProtocol: 'deepseek',
      resolvedModel: 'deepseek/deepseek-flash',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.siliconflow.cn/v1' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash,deepseek-v4-pro' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/聊天调用 · 模型不可用：LLM channel test failed/i)).toBeInTheDocument();
    expect(screen.getByText(/本次测试模型：deepseek\/deepseek-flash/i)).toBeInTheDocument();
    expect(screen.getByText(/基础连接测试默认使用模型列表首项：deepseek-flash/i)).toBeInTheDocument();
    expect(screen.getByText(/基础连接测试默认只测试模型列表中的第一个模型/i)).toBeInTheDocument();
    expect(screen.getByText(/调整模型顺序或移除不可用模型/i)).toBeInTheDocument();
    expect(screen.getByText(/模型是否已开通、账号是否可见/i)).toBeInTheDocument();
    expect(screen.queryByText(/Base URL、代理、TLS/i)).not.toBeInTheDocument();
    expect(testLLMChannel).toHaveBeenCalledWith(expect.objectContaining({
      models: ['deepseek-flash', 'deepseek-v4-pro'],
    }));
  });

  it('shows provider blocked troubleshooting without network or model-list hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request was blocked by provider or gateway policy',
      error: 'litellm.APIError: APIError: OpenAIException - Your request was blocked.',
      errorCode: 'request_blocked',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'provider_blocked', model: 'deepseek/deepseek-v4-pro' },
      resolvedProtocol: 'deepseek',
      resolvedModel: 'deepseek/deepseek-v4-pro',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'proxy' },
          { key: 'LLM_PROXY_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_PROXY_BASE_URL', value: 'https://gateway.example.com/v1' },
          { key: 'LLM_PROXY_ENABLED', value: 'true' },
          { key: 'LLM_PROXY_API_KEY', value: 'secret-key' },
          { key: 'LLM_PROXY_MODELS', value: 'deepseek-v4-pro,deepseek-flash' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /proxy/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/聊天调用 · 请求被拦截/i)).toBeInTheDocument();
    expect(screen.getByText(/本次测试模型：deepseek\/deepseek-v4-pro/i)).toBeInTheDocument();
    expect(screen.getByText(/账号风控、地域限制、模型权限/i)).toBeInTheDocument();
    expect(screen.queryByText(/Base URL、代理、TLS/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/调整模型顺序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('shows focused quota exceeded troubleshooting hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request was rejected by quota or rate limiting',
      error: 'quota exceeded',
      errorCode: 'quota',
      stage: 'chat_completion',
      retryable: true,
      details: { reason: 'quota_exceeded' },
      resolvedProtocol: 'deepseek',
      resolvedModel: 'deepseek/deepseek-flash',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' }, { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' }, { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' }, { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/服务商返回配额已耗尽/i)).toBeInTheDocument();
    expect(screen.queryByText(/调整模型顺序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('does not show model-list action hints for network failures', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request failed before a valid response was returned',
      error: 'DNS lookup failed',
      errorCode: 'network_error',
      stage: 'chat_completion',
      retryable: true,
      details: { reason: 'dns_error' },
      resolvedProtocol: 'deepseek',
      resolvedModel: 'deepseek/deepseek-flash',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' }, { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' }, { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' }, { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/域名解析失败/i)).toBeInTheDocument();
    expect(screen.queryByText(/调整模型顺序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('does not request runtime capabilities during the basic connection test', async () => {
    testLLMChannel.mockResolvedValue({
      success: true,
      message: 'LLM channel test succeeded',
      error: null,
      errorCode: null,
      stage: 'chat_completion',
      retryable: false,
      details: {},
      resolvedProtocol: 'deepseek',
      resolvedModel: 'deepseek/deepseek-flash',
      latencyMs: 80,
      capabilityResults: {},
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' }, { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' }, { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' }, { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    await screen.findByText(/连接成功 · deepseek\/deepseek-flash/i);
    expect(testLLMChannel).toHaveBeenCalledWith(expect.not.objectContaining({ capabilityChecks: expect.anything() }));
  });

  it('runs explicit runtime capability checks and shows detailed hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: true,
      message: 'LLM channel test succeeded',
      error: null,
      errorCode: null,
      stage: 'chat_completion',
      retryable: false,
      details: {},
      resolvedProtocol: 'deepseek',
      resolvedModel: 'deepseek/deepseek-flash',
      latencyMs: 80,
      capabilityResults: {
        json: {
          status: 'passed',
          message: 'JSON output capability check passed',
          errorCode: null,
          stage: 'capability_json',
          retryable: false,
          details: { reason: 'json_valid' },
        },
        tools: {
          status: 'failed',
          message: 'LLM channel does not support tools capability',
          errorCode: 'capability_unsupported',
          stage: 'capability_tools',
          retryable: false,
          details: { reason: 'capability_unsupported' },
        },
      },
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' }, { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' }, { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' }, { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByLabelText('JSON'));
    fireEvent.click(screen.getByLabelText('Tools'));
    fireEvent.click(screen.getByRole('button', { name: '检测能力' }));

    expect(await screen.findByText(/能力检测完成：1 通过 \/ 1 失败 \/ 0 跳过/i)).toBeInTheDocument();
    expect(screen.getByText('JSON 通过')).toBeInTheDocument();
    expect(screen.getByText('Tools 失败')).toBeInTheDocument();
    expect(screen.getByText(/当前模型或兼容层不支持该能力/i)).toBeInTheDocument();
    expect(testLLMChannel).toHaveBeenCalledWith(expect.objectContaining({ capabilityChecks: ['json', 'tools'] }));
  });

  it('shows skipped runtime capabilities when the base test fails', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM authentication failed',
      error: '401 Unauthorized',
      errorCode: 'auth',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'api_key_rejected' },
      resolvedProtocol: 'deepseek',
      resolvedModel: 'deepseek/deepseek-flash',
      latencyMs: null,
      capabilityResults: {
        json: {
          status: 'skipped',
          message: 'Skipped because the base channel test did not pass',
          errorCode: 'skipped',
          stage: 'capability_json',
          retryable: false,
          details: { reason: 'base_test_failed' },
        },
      },
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' }, { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' }, { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' }, { key: 'LLM_DEEPSEEK_API_KEY', value: 'bad-key' }, { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-flash' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByLabelText('JSON'));
    fireEvent.click(screen.getByRole('button', { name: '检测能力' }));

    expect(await screen.findByText(/能力检测完成：0 通过 \/ 0 失败 \/ 1 跳过/i)).toBeInTheDocument();
    expect(screen.getByText('JSON 跳过')).toBeInTheDocument();
    expect(screen.getByText(/服务商拒绝了当前 API Key/i)).toBeInTheDocument();
    expect(screen.getByLabelText('模型（逗号分隔）')).toBeEnabled();
  });

  it('keeps manual model input available when discovery fails', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'Model discovery is not supported for this protocol',
      error: 'LLM channel does not support /models discovery yet',
      errorCode: 'unsupported_protocol',
      stage: 'model_discovery',
      retryable: false,
      details: {},
      resolvedProtocol: 'deepseek',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: '' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    await screen.findByText(/模型发现 · 协议暂不支持：Model discovery is not supported for this protocol/i);
    expect(screen.getByText(/当前仅对 DeepSeek 渠道提供自动模型发现/i)).toBeInTheDocument();

    const manualInput = screen.getByLabelText('模型（逗号分隔）');
    fireEvent.change(manualInput, { target: { value: 'gemini-2.5-flash' } });
    expect(manualInput).toHaveValue('gemini-2.5-flash');
  });

  it('maps discovery format errors to the /models troubleshooting hint', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'Failed to parse /models response',
      error: 'Unexpected discovery payload',
      errorCode: 'format_error',
      stage: 'response_parse',
      retryable: false,
      details: {},
      resolvedProtocol: 'deepseek',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' },
          { key: 'LLM_DEEPSEEK_MODELS', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    expect(await screen.findByText(/响应解析 · 格式异常：Failed to parse \/models response/i)).toBeInTheDocument();
    expect(screen.getByText(/该渠道返回的 \/models 响应格式不兼容，请改为手动填写模型列表。/i)).toBeInTheDocument();
  });

  it('maps discovery empty responses to the /models troubleshooting hint', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'No model IDs returned from /models response',
      error: 'Empty model discovery response',
      errorCode: 'empty_response',
      stage: 'model_discovery',
      retryable: false,
      details: {},
      resolvedProtocol: 'deepseek',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'secret-key' },
          { key: 'LLM_DEEPSEEK_MODELS', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    expect(await screen.findByText(/模型发现 · 空响应：No model IDs returned from \/models response/i)).toBeInTheDocument();
    expect(screen.getByText(/该渠道的 \/models 接口未返回可用模型 ID/i)).toBeInTheDocument();
    expect(screen.queryByText(/切换兼容模型、关闭额外响应模式/i)).not.toBeInTheDocument();
  });

  it('does not apply stale discovery response after channel list re-sync', async () => {
    let resolvePendingFirst!: (value: unknown) => void;
    const pendingFirst = new Promise((resolve) => {
      resolvePendingFirst = resolve;
    });

    discoverLLMChannelModels
      .mockImplementationOnce(() => pendingFirst)
      .mockResolvedValueOnce({
        success: true,
        message: 'LLM channel model discovery succeeded',
        error: null,
        resolvedProtocol: 'deepseek',
        models: ['dashscope-plus'],
        latencyMs: 30,
      });

    const renderResult = render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'open-key' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'gpt-old' },
          { key: 'LLM_SECONDARY_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_SECONDARY_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_SECONDARY_ENABLED', value: 'true' },
          { key: 'LLM_SECONDARY_API_KEY', value: 'dash-key' },
          { key: 'LLM_SECONDARY_MODELS', value: 'dash-old' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    renderResult.rerender(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'secondary' },
          { key: 'LLM_SECONDARY_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_SECONDARY_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_SECONDARY_ENABLED', value: 'true' },
          { key: 'LLM_SECONDARY_API_KEY', value: 'dash-key' },
          { key: 'LLM_SECONDARY_MODELS', value: 'dash-old' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /secondary/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const dashModelCheckbox = await screen.findByLabelText('dashscope-plus');
    fireEvent.click(dashModelCheckbox);

    expect(screen.getByLabelText('手动模型（逗号分隔）')).toHaveValue('dash-old,dashscope-plus');

    resolvePendingFirst({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'deepseek',
      models: ['stale-openai'],
      latencyMs: 20,
    });

    await waitFor(() => {
      expect(screen.getByLabelText('手动模型（逗号分隔）')).toHaveValue('dash-old,dashscope-plus');
    });
    expect(screen.queryByLabelText('stale-openai')).not.toBeInTheDocument();
  });

  it('does not apply stale discovery response after inline channel edit', async () => {
    let resolvePendingFirst!: (value: unknown) => void;
    const pendingFirst = new Promise((resolve) => {
      resolvePendingFirst = resolve;
    });

    discoverLLMChannelModels.mockImplementationOnce(() => pendingFirst);

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'dash-key' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'qwen-old' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const baseUrlInput = screen.getByLabelText('Base URL');
    fireEvent.change(baseUrlInput, {
      target: { value: 'https://dashscope.aliyuncs.com/compatible-mode/v2' },
    });

    resolvePendingFirst({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'deepseek',
      models: ['stale-openai'],
      latencyMs: 20,
    });

    await waitFor(() => {
      expect(screen.getByLabelText('模型（逗号分隔）')).toHaveValue('qwen-old');
      expect(screen.queryByLabelText('stale-openai')).not.toBeInTheDocument();
    });
  });
});
