import { createServer } from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import * as actual from '@actual-app/api';
import { SummaryCache, collectSummary } from './lib.js';

const REQUIRED_ENVIRONMENT = [
  'ACTUAL_SERVER_URL',
  'ACTUAL_PASSWORD',
  'ACTUAL_BUDGET_SYNC_ID',
  'CYD_API_TOKEN',
];

function requireEnvironment(environment) {
  for (const name of REQUIRED_ENVIRONMENT) {
    if (!environment[name]) {
      throw new Error(`${name} must be configured`);
    }
  }
}

function authorized(authorization, token) {
  if (typeof authorization !== 'string' || !authorization.startsWith('Bearer ')) {
    return false;
  }

  const candidate = Buffer.from(authorization.slice('Bearer '.length));
  const expected = Buffer.from(token);
  return candidate.length === expected.length && timingSafeEqual(candidate, expected);
}

function json(response, status, body) {
  response.writeHead(status, {
    'Cache-Control': 'no-store',
    'Content-Type': 'application/json; charset=utf-8',
  });
  response.end(JSON.stringify(body));
}

export function createSummaryLoader(api, environment, now = () => new Date()) {
  return async () => {
    let initialized = false;
    try {
      await api.init({
        dataDir: environment.ACTUAL_DATA_DIR || '/tmp/actual-data',
        serverURL: environment.ACTUAL_SERVER_URL,
        password: environment.ACTUAL_PASSWORD,
      });
      initialized = true;
      await api.downloadBudget(environment.ACTUAL_BUDGET_SYNC_ID, {
        password: environment.ACTUAL_BUDGET_PASSWORD || undefined,
      });
      return await collectSummary(api, now);
    } finally {
      if (initialized) {
        await api.shutdown();
      }
    }
  };
}

export function createHttpServer({ api = actual, environment = process.env, now = () => new Date() } = {}) {
  requireEnvironment(environment);
  const cache = new SummaryCache({ load: createSummaryLoader(api, environment, now) });

  return createServer(async (request, response) => {
    if (request.method === 'GET' && request.url === '/healthz') {
      response.writeHead(204);
      response.end();
      return;
    }

    if (request.method !== 'GET' || request.url !== '/v1/summary') {
      json(response, 404, { error: 'not found' });
      return;
    }

    if (!authorized(request.headers.authorization, environment.CYD_API_TOKEN)) {
      json(response, 401, { error: 'unauthorized' });
      return;
    }

    try {
      json(response, 200, await cache.get());
    } catch (error) {
      console.error('Unable to refresh finance summary', error instanceof Error ? error.message : error);
      json(response, 503, { error: 'summary unavailable' });
    }
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const server = createHttpServer();
  server.listen(8080, '0.0.0.0', () => {
    console.info('finance-display listening on :8080');
  });
}
