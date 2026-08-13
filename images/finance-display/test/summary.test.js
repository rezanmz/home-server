import assert from 'node:assert/strict';
import test from 'node:test';
import { SummaryCache, collectSummary } from '../lib.js';

test('collectSummary sums open assets and debts but excludes closed accounts', async () => {
  const balances = new Map([
    ['cash', 123_456],
    ['loan', -50_000],
    ['closed', 999_999],
  ]);
  const actual = {
    getAccounts: async () => [
      { id: 'cash', closed: false, last_reconciled: '2026-08-12' },
      { id: 'loan', closed: false, last_reconciled: '2026-08-03' },
      { id: 'closed', closed: true, last_reconciled: '2000-01-01' },
    ],
    getPreferences: async () => ({ currency: 'CAD' }),
    getAccountBalance: async (id) => balances.get(id),
  };

  const summary = await collectSummary(actual, () => new Date('2026-08-13T12:00:00.000Z'));

  assert.deepEqual(summary, {
    netWorthCents: 73_456,
    currency: 'CAD',
    lastReconciledOn: '2026-08-12',
    oldestReconciledOn: '2026-08-03',
    oldestReconciledDaysAgo: 10,
    asOf: '2026-08-13T12:00:00.000Z',
  });
});
test('collectSummary omits reconciliation freshness when no open account has a valid date', async () => {
  const actual = {
    getAccounts: async () => [
      { id: 'open-invalid', closed: false, last_reconciled: 'not-a-date' },
      { id: 'open-never', closed: false, last_reconciled: null },
      { id: 'closed', closed: true, last_reconciled: '2020-01-01' },
    ],
    getPreferences: async () => ({}),
    getAccountBalance: async () => 0,
  };

  const summary = await collectSummary(actual, () => new Date('2026-08-13T12:00:00.000Z'));

  assert.deepEqual(summary, {
    netWorthCents: 0,
    currency: null,
    lastReconciledOn: null,
    oldestReconciledOn: null,
    oldestReconciledDaysAgo: null,
    asOf: '2026-08-13T12:00:00.000Z',
  });
});


test('SummaryCache serves a stale last-known value after refresh failure', async () => {
  let now = Date.parse('2026-08-13T12:00:00.000Z');
  let attempt = 0;
  const cache = new SummaryCache({
    now: () => now,
    cacheMs: 1_000,
    retryMs: 60_000,
    load: async () => {
      attempt += 1;
      if (attempt === 2) throw new Error('Actual unavailable');
      return {
        netWorthCents: 73_456,
        currency: 'CAD',
        asOf: new Date(now).toISOString(),
      };
    },
  });

  assert.deepEqual(await cache.get(), {
    netWorthCents: 73_456,
    currency: 'CAD',
    asOf: '2026-08-13T12:00:00.000Z',
    stale: false,
  });

  now += 1_001;
  assert.deepEqual(await cache.get(), {
    netWorthCents: 73_456,
    currency: 'CAD',
    asOf: '2026-08-13T12:00:00.000Z',
    stale: true,
  });
  assert.equal(attempt, 2);
});

test('SummaryCache coalesces simultaneous refreshes', async () => {
  let calls = 0;
  let resolve;
  const loading = new Promise((done) => {
    resolve = done;
  });
  const cache = new SummaryCache({
    load: async () => {
      calls += 1;
      await loading;
      return {
        netWorthCents: 1,
        currency: 'CAD',
        asOf: new Date().toISOString(),
      };
    },
  });

  const first = cache.get();
  const second = cache.get();
  resolve();
  await Promise.all([first, second]);

  assert.equal(calls, 1);
});
