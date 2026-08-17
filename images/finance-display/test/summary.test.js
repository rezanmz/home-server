import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  DISPLAY_CACHE_MS,
  FocusState,
  SummaryCache,
  WEATHER_CACHE_MS,
  WeatherCache,
  collectSummary,
  normalizeWeather,
  themeForTime,
} from '../lib.js';

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
            last_reconciled: String(Date.parse('2026-08-12T21:00:00.000Z')),
          },
          {
            name: 'Loan',
            closed: false,
            last_reconciled: String(Date.parse('2026-08-03T21:00:00.000Z')),
          },
          { name: 'Closed', closed: true, last_reconciled: '2000-01-01' },
        ],
      };
    },
  };

  const summary = await collectSummary(
    actual,
    () => new Date('2026-08-13T12:00:00.000Z'),
    'America/Toronto',
  );

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

  const summary = await collectSummary(
    actual,
    () => new Date('2026-08-13T12:00:00.000Z'),
    'America/Toronto',
  );

  assert.deepEqual(summary, {
    netWorthCents: 0,
    currency: null,
    oldestReconciledAccountName: null,
    oldestReconciledOn: null,
    oldestReconciledDaysAgo: null,
    asOf: '2026-08-13T12:00:00.000Z',
  });
});

test('collectSummary advances reconciliation age at local midnight', async () => {
  const reconciledAt = String(Date.parse('2026-08-12T21:00:00.000Z'));
  const actual = {
    getAccounts: async () => [{ id: 'cash', closed: false }],
    getPreferences: async () => ({ currency: 'CAD' }),
    getAccountBalance: async () => 0,
    q: () => ({ select: () => ({}) }),
    aqlQuery: async () => ({
      data: [{ name: 'Cash', closed: false, last_reconciled: reconciledAt }],
    }),
  };

  const beforeMidnight = await collectSummary(
    actual,
    () => new Date('2026-08-13T03:59:59.999Z'),
    'America/Toronto',
  );
  const atMidnight = await collectSummary(
    actual,
    () => new Date('2026-08-13T04:00:00.000Z'),
    'America/Toronto',
  );

  assert.equal(beforeMidnight.oldestReconciledDaysAgo, 0);
  assert.equal(atMidnight.oldestReconciledDaysAgo, 1);
  assert.equal(atMidnight.oldestReconciledOn, '2026-08-12');
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

test('SummaryCache refreshes the display data every 15 seconds by default', async () => {
  let now = Date.parse('2026-08-13T12:00:00.000Z');
  let calls = 0;
  const cache = new SummaryCache({
    now: () => now,
    load: async () => {
      calls += 1;
      return {
        netWorthCents: calls,
        currency: 'CAD',
        asOf: new Date(now).toISOString(),
      };
    },
  });

  await cache.get();
  now += DISPLAY_CACHE_MS - 1;
  await cache.get();
  assert.equal(calls, 1);

  now += 1;
  await cache.get();
  assert.equal(calls, 2);
});

test('normalizeWeather maps WMO conditions and solar times into display data', () => {
  assert.deepEqual(
    normalizeWeather({
      time: Date.parse('2026-08-13T23:10:00.000Z') / 1000,
      temperature_2m: -2.6,
      weather_code: 85,
      is_day: 0,
    }, {
      sunrise: [Date.parse('2026-08-13T12:20:00.000Z') / 1000],
      sunset: [Date.parse('2026-08-14T02:20:00.000Z') / 1000],
    }),
    {
      condition: 'snow',
      label: 'SNOW',
      weatherCode: 85,
      isDay: false,
      temperatureC: -3,
      observedAt: '2026-08-13T23:10:00.000Z',
      sunriseAt: '2026-08-13T12:20:00.000Z',
      sunsetAt: '2026-08-14T02:20:00.000Z',
    },
  );
});

test('themeForTime gradually follows local sunrise and sunset', () => {
  const weather = {
    sunriseAt: '2026-08-13T10:00:00.000Z',
    sunsetAt: '2026-08-14T00:00:00.000Z',
  };

  assert.deepEqual(
    themeForTime(weather, new Date('2026-08-13T12:00:00.000Z'), 'America/Toronto'),
    {
      localTime: '8:00',
      localPeriod: 'AM',
      sunrise: '6:00 AM',
      sunset: '8:00 PM',
      darknessPercent: 0,
    },
  );
  assert.equal(
    themeForTime(weather, new Date('2026-08-14T00:00:00.000Z'), 'America/Toronto')
      .darknessPercent,
    50,
  );
  assert.equal(
    themeForTime(weather, new Date('2026-08-14T02:00:00.000Z'), 'America/Toronto')
      .darknessPercent,
    100,
  );
});

test('WeatherCache keeps weather refreshes separate from fast display polling', async () => {
  let now = 1_000;
  let calls = 0;
  const cache = new WeatherCache({
    now: () => now,
    load: async () => ({ condition: 'clear', weatherCode: calls++ }),
  });

  assert.equal((await cache.get()).weatherCode, 0);
  now += WEATHER_CACHE_MS - 1;
  assert.equal((await cache.get()).weatherCode, 0);
  now += 1;
  assert.equal((await cache.get()).weatherCode, 1);
  assert.equal(calls, 2);
});

test('FocusState persists the desired boolean across process replacement', (t) => {
  const stateDirectory = mkdtempSync(join(tmpdir(), 'finance-display-focus-'));
  const statePath = join(stateDirectory, 'focus-state.json');
  t.after(() => rmSync(stateDirectory, { force: true, recursive: true }));

  const first = new FocusState({
    now: () => new Date('2026-08-13T12:00:00.000Z'),
    statePath,
  });
  assert.deepEqual(first.snapshot(), { focusMode: false, focusUpdatedAt: null });
  assert.deepEqual(first.set(true), {
    focusMode: true,
    focusUpdatedAt: '2026-08-13T12:00:00.000Z',
  });

  const replacement = new FocusState({
    now: () => new Date('2026-08-13T12:05:00.000Z'),
    statePath,
  });
  assert.deepEqual(replacement.snapshot(), {
    focusMode: true,
    focusUpdatedAt: '2026-08-13T12:00:00.000Z',
  });
  assert.throws(() => replacement.set('true'), /must be a boolean/);
});
