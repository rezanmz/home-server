import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import test from 'node:test';
import { createHttpServer, createWeatherLoader } from '../server.js';

function environment(t) {
  const stateDirectory = mkdtempSync(join(tmpdir(), 'finance-display-focus-'));
  t.after(() => rmSync(stateDirectory, { force: true, recursive: true }));
  return {
    ACTUAL_SERVER_URL: 'http://actual.test:5006',
    ACTUAL_PASSWORD: 'actual-password',
    ACTUAL_BUDGET_SYNC_ID: 'budget-id',
    CYD_API_TOKEN: 'display-token',
    WEATHER_LATITUDE: '43.6532',
    WEATHER_LONGITUDE: '-79.3832',
    LOCAL_TIME_ZONE: 'America/Toronto',
    FOCUS_STATE_PATH: join(stateDirectory, 'focus-state.json'),
  };
}

function fakeWeather() {
  return async () =>
    new Response(
      JSON.stringify({
        current: {
          time: Date.parse('2026-08-13T12:00:00.000Z') / 1000,
          temperature_2m: 24.4,
          weather_code: 2,
          is_day: 1,
        },
        daily: {
          sunrise: [Date.parse('2026-08-13T10:00:00.000Z') / 1000],
          sunset: [Date.parse('2026-08-14T00:00:00.000Z') / 1000],
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
}

function fakeActual() {
  const calls = [];
  return {
    calls,
    init: async (configuration) => calls.push(['init', configuration]),
    downloadBudget: async (...arguments_) => calls.push(['downloadBudget', arguments_]),
    getAccounts: async () => [{ id: 'cash', closed: false }],
    getPreferences: async () => ({ currency: 'CAD' }),
    getAccountBalance: async () => 12_345,
    q: (table) => ({ select: (fields) => ({ table, fields }) }),
    aqlQuery: async () => ({
      data: [{ name: 'Cash', closed: false, last_reconciled: '2026-08-12' }],
    }),
    shutdown: async () => calls.push(['shutdown']),
  };
}

async function request(server, path, { headers = {}, method = 'GET', body } = {}) {
  const response = await fetch(`http://127.0.0.1:${server.address().port}${path}`, {
    headers,
    method,
    body,
  });
  return { status: response.status, body: await response.json() };
}

test('summary endpoint requires the display bearer token', async (t) => {
  const api = fakeActual();
  const server = createHttpServer({
    api,
    environment: environment(t),
    fetchImplementation: fakeWeather(),
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => server.close());

  assert.deepEqual(await request(server, '/v1/summary'), {
    status: 401,
    body: { error: 'unauthorized' },
  });
  assert.deepEqual(api.calls, []);
});

test('summary endpoint returns only the derived display payload', async (t) => {
  const api = fakeActual();
  const server = createHttpServer({
    api,
    environment: environment(t),
    now: () => new Date('2026-08-13T12:00:00.000Z'),
    fetchImplementation: fakeWeather(),
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => server.close());

  const result = await request(server, '/v1/summary', {
    headers: { Authorization: 'Bearer display-token' },
  });

  assert.equal(result.status, 200);
  assert.equal(result.body.netWorthCents, 12_345);
  assert.equal(result.body.currency, 'CAD');
  assert.equal(result.body.reconciliationStatus, 'due');
  assert.equal(result.body.oldestReconciledAccountName, 'Cash');
  assert.equal(result.body.oldestReconciledOn, '2026-08-12');
  assert.equal(result.body.oldestReconciledDaysAgo, 1);
  assert.equal(result.body.focusMode, false);
  assert.equal(result.body.focusUpdatedAt, null);
  assert.deepEqual(result.body.weather, {
    condition: 'cloudy',
    label: 'PARTLY CLOUDY',
    weatherCode: 2,
    isDay: true,
    temperatureC: 24,
    observedAt: '2026-08-13T12:00:00.000Z',
    sunriseAt: '2026-08-13T10:00:00.000Z',
    sunsetAt: '2026-08-14T00:00:00.000Z',
    stale: false,
    theme: {
      localTime: '8:00',
      localPeriod: 'AM',
      sunrise: '6:00 AM',
      sunset: '8:00 PM',
      darknessPercent: 0,
    },
  });
  assert.match(result.body.asOf, /^\d{4}-\d{2}-\d{2}T/);
  assert.deepEqual(api.calls, [
    ['init', {
      dataDir: '/tmp/actual-data',
      serverURL: 'http://actual.test:5006',
      password: 'actual-password',
    }],
    ['downloadBudget', ['budget-id', { password: undefined }]],
    ['shutdown'],
  ]);
});

test('weather loader requests one local day with solar events', async (t) => {
  const configured = environment(t);
  let requested;
  const load = createWeatherLoader(configured, async (url) => {
    requested = url;
    return fakeWeather()();
  });

  await load();

  assert.equal(requested.searchParams.get('daily'), 'sunrise,sunset');
  assert.equal(requested.searchParams.get('timezone'), 'America/Toronto');
  assert.equal(requested.searchParams.get('forecast_days'), '1');
  assert.equal(requested.searchParams.get('timeformat'), 'unixtime');
});

test('server rejects an invalid local timezone at startup', (t) => {
  const configured = environment(t);
  configured.LOCAL_TIME_ZONE = 'Not/A_Time_Zone';
  assert.throws(
    () => createHttpServer({ environment: configured, api: fakeActual(), fetchImplementation: fakeWeather() }),
    /valid IANA time zone/,
  );
});

test('focus mode is an authenticated idempotent update shared with summary readers', async (t) => {
  const api = fakeActual();
  const server = createHttpServer({
    api,
    environment: environment(t),
    now: () => new Date('2026-08-13T12:00:00.000Z'),
    fetchImplementation: fakeWeather(),
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => server.close());

  const authorization = { Authorization: 'Bearer display-token' };
  assert.deepEqual(
    await request(server, '/v1/summary', {
      method: 'PUT',
      headers: { ...authorization, 'Content-Type': 'application/json' },
      body: JSON.stringify({ focusMode: true }),
    }),
    {
      status: 200,
      body: { focusMode: true, focusUpdatedAt: '2026-08-13T12:00:00.000Z' },
    },
  );

  const summary = await request(server, '/v1/summary', { headers: authorization });
  assert.equal(summary.status, 200);
  assert.equal(summary.body.focusMode, true);
  assert.equal(summary.body.focusUpdatedAt, '2026-08-13T12:00:00.000Z');
});

test('focus mode rejects missing authorization and non-boolean values', async (t) => {
  const server = createHttpServer({
    api: fakeActual(),
    environment: environment(t),
    fetchImplementation: fakeWeather(),
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => server.close());

  const body = JSON.stringify({ focusMode: 'yes' });
  assert.deepEqual(
    await request(server, '/v1/summary', { method: 'PUT', body }),
    { status: 401, body: { error: 'unauthorized' } },
  );
  assert.deepEqual(
    await request(server, '/v1/summary', {
      method: 'PUT',
      headers: { Authorization: 'Bearer display-token' },
      body,
    }),
    { status: 400, body: { error: 'focusMode must be a boolean' } },
  );
});
