import { createServer } from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import * as actual from '@actual-app/api';
import {
  FocusState,
  SummaryCache,
  WeatherCache,
  collectSummary,
  normalizeWeather,
  themeForTime,
  validateTimeZone,
} from './lib.js';

const REQUIRED_ENVIRONMENT = [
  'ACTUAL_SERVER_URL',
  'ACTUAL_PASSWORD',
  'ACTUAL_BUDGET_SYNC_ID',
  'CYD_API_TOKEN',
  'WEATHER_LATITUDE',
  'WEATHER_LONGITUDE',
  'LOCAL_TIME_ZONE',
  'FOCUS_STATE_PATH',
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

async function requestJson(request, maximumBytes = 1024) {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > maximumBytes) {
      const error = new Error('request body is too large');
      error.status = 413;
      throw error;
    }
    chunks.push(chunk);
  }

  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    const error = new Error('request body must be valid JSON');
    error.status = 400;
    throw error;
  }
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
      return await collectSummary(api, now, environment.LOCAL_TIME_ZONE);
    } finally {
      if (initialized) {
        await api.shutdown();
      }
    }
  };
}

export function createWeatherLoader(environment, fetchImplementation = fetch) {
  const latitude = Number(environment.WEATHER_LATITUDE);
  const longitude = Number(environment.WEATHER_LONGITUDE);
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
    throw new Error('WEATHER_LATITUDE must be a valid coordinate');
  }
  if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
    throw new Error('WEATHER_LONGITUDE must be a valid coordinate');
  }

  const url = new URL('https://api.open-meteo.com/v1/forecast');
  url.searchParams.set('latitude', String(latitude));
  url.searchParams.set('longitude', String(longitude));
  url.searchParams.set('current', 'temperature_2m,weather_code,is_day');
  url.searchParams.set('daily', 'sunrise,sunset');
  url.searchParams.set('timezone', environment.LOCAL_TIME_ZONE);
  url.searchParams.set('forecast_days', '1');
  url.searchParams.set('timeformat', 'unixtime');

  return async () => {
    const response = await fetchImplementation(url, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) {
      throw new Error(`weather request returned HTTP ${response.status}`);
    }
    const body = await response.json();
    return normalizeWeather(body.current, body.daily);
  };
}

export function createHttpServer({
  api = actual,
  environment = process.env,
  now = () => new Date(),
  fetchImplementation = fetch,
  focusState,
} = {}) {
  requireEnvironment(environment);
  validateTimeZone(environment.LOCAL_TIME_ZONE);
  const persistedFocusState = focusState || new FocusState({
    now,
    statePath: environment.FOCUS_STATE_PATH,
  });
  const cache = new SummaryCache({ load: createSummaryLoader(api, environment, now) });
  const weatherCache = new WeatherCache({
    load: createWeatherLoader(environment, fetchImplementation),
  });
  let weatherErrorLogged = false;

  return createServer(async (request, response) => {
    if (request.method === 'GET' && request.url === '/healthz') {
      response.writeHead(204);
      response.end();
      return;
    }

    if (request.url !== '/v1/summary') {
      json(response, 404, { error: 'not found' });
      return;
    }

    if (!authorized(request.headers.authorization, environment.CYD_API_TOKEN)) {
      json(response, 401, { error: 'unauthorized' });
      return;
    }

    if (request.method === 'PUT') {
      try {
        const body = await requestJson(request);
        if (typeof body?.focusMode !== 'boolean') {
          json(response, 400, { error: 'focusMode must be a boolean' });
          return;
        }
        json(response, 200, persistedFocusState.set(body.focusMode));
      } catch (error) {
        const status = error.status || 500;
        json(response, status, {
          error: error.status ? error.message : 'focus state unavailable',
        });
      }
      return;
    }

    if (request.method !== 'GET') {
      response.setHeader('Allow', 'GET, PUT');
      json(response, 405, { error: 'method not allowed' });
      return;
    }

    try {
      const [summary, weather] = await Promise.all([
        cache.get(),
        weatherCache.get().then(
          (value) => {
            weatherErrorLogged = false;
            return {
              ...value,
              theme: themeForTime(value, now(), environment.LOCAL_TIME_ZONE),
            };
          },
          (error) => {
            if (!weatherErrorLogged) {
              console.error(
                'Unable to refresh current weather',
                error instanceof Error ? error.message : error,
              );
              weatherErrorLogged = true;
            }
            return null;
          },
        ),
      ]);
      json(response, 200, { ...summary, ...persistedFocusState.snapshot(), weather });
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
