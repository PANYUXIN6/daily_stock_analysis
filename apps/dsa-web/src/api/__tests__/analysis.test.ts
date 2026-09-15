import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../analysis';

const post = vi.hoisted(() => vi.fn());

vi.mock('../index', () => ({
  default: {
    get: vi.fn(),
    post,
  },
}));

describe('analysisApi.triggerMarketReview', () => {
  beforeEach(() => {
    post.mockReset();
    post.mockResolvedValue({
      status: 202,
      data: {
        status: 'accepted',
        message: 'accepted',
        send_notification: true,
        region: 'cn',
        task_id: 'market-task-1',
      },
    });
  });

  it('serializes selected markets to a comma-separated request string', async () => {
    const result = await analysisApi.triggerMarketReview({
      sendNotification: false,
      regions: ['cn'],
    });

    expect(post).toHaveBeenCalledWith(
      '/api/v1/analysis/market-review',
      {
        send_notification: false,
        report_language: undefined,
        region: 'cn',
      },
      expect.any(Object),
    );
    expect(result.region).toBe('cn');
  });

  it('omits region when the caller inherits the server default', async () => {
    await analysisApi.triggerMarketReview({ sendNotification: true });

    expect(post).toHaveBeenCalledWith(
      '/api/v1/analysis/market-review',
      {
        send_notification: true,
        report_language: undefined,
      },
      expect.any(Object),
    );
  });
});
