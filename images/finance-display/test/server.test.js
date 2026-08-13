import assert from 'node:assert/strict';
import { once } from 'node:events';
import test from 'node:test';
import { createHttpServer } from '../server.js';

function environment() {
  return {
    ACTUAL_SERVER_URL: 'http://actual.test:5006',
    ACTUAL_PASSWORD: 'actual-password',
    ACTUAL_BUDGET_SYNC_ID: 'budget-id',
    CYD_API_TOKEN: 'display-token',
  };
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
    shutdown: async () => calls.push(['shutdown']),
  };
}

async function request(server, path, headers = {}) {
  const response = await fetch(`http://127.0.0.1:${server.address().port}${path}`, { headers });
  return { status: response.status, body: await response.json() };
}

test('summary endpoint requires the display bearer token', async (t) => {
  const api = fakeActual();
  const server = createHttpServer({ api, environment: environment() });
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
  const server = createHttpServer({ api, environment: environment() });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => server.close());

  const result = await request(server, '/v1/summary', {
    Authorization: 'Bearer display-token',
  });

  assert.equal(result.status, 200);
  assert.equal(result.body.netWorthCents, 12_345);
  assert.equal(result.body.currency, 'CAD');
  assert.equal(result.body.stale, false);
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
