import assert from 'node:assert/strict';
import test from 'node:test';
import { SummaryCache, collectSummary } from '../lib.js';

test('collectSummary uses the oldest open ActualQL reconciliation timestamp', async () => {
  const balances = new Map([
    ['cash', 123_456],
    ['loan', -50_000],
    ['closed', 999_999],
  ]);
  let reconciliationQuery;
  const actual = {
    getAccounts: async () => [
      { id: 'cash', closed: false },
      { id: 'loan', closed: false },
      { id: 'closed', closed: true },
    ],
    getPreferences: async () => ({ currency: 'CAD' }),
    getAccountBalance: async (id) => balances.get(id),
    q: (table) => ({ select: (fields) => ({ table, fields }) }),
    aqlQuery: async (query) => {
      reconciliationQuery = query;
      return {
        data: [
          {
            name: 'Cash',
            closed: false,
            last_reconciled: String(Date.parse('2026-08-12T00:00:00.000Z')),
          },
          {
            name: 'Loan',
            closed: false,
            last_reconciled: String(Date.parse('2026-08-03T00:00:00.000Z')),
          },
          { name: 'Closed', closed: true, last_reconciled: '2000-01-01' },
        ],
      };
    },
  };

  const summary = await collectSummary(actual, () => new Date('2026-08-13T12:00:00.000Z'));

  assert.deepEqual(summary, {
    netWorthCents: 73_456,
    currency: 'CAD',
    oldestReconciledAccountName: 'Loan',
    oldestReconciledOn: '2026-08-03',
    oldestReconciledDaysAgo: 10,
    asOf: '2026-08-13T12:00:00.000Z',
  });
  assert.deepEqual(reconciliationQuery, {
    table: 'accounts',
    fields: ['name', 'closed', 'last_reconciled'],
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
    q: () => ({ select: () => ({}) }),
    aqlQuery: async () => ({
      data: [
        { name: 'Invalid', closed: false, last_reconciled: 'not-a-date' },
        { name: 'Never', closed: false, last_reconciled: null },
        { name: 'Closed', closed: true, last_reconciled: '2020-01-01' },
      ],
    }),
  };

  const summary = await collectSummary(actual, () => new Date('2026-08-13T12:00:00.000Z'));

  assert.deepEqual(summary, {
    netWorthCents: 0,
    currency: null,
    oldestReconciledAccountName: null,
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
