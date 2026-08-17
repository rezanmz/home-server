import { readFileSync, renameSync, writeFileSync } from 'node:fs';

export const CENTS_PER_UNIT = 100;
export const DISPLAY_CACHE_MS = 15_000;
export const WEATHER_CACHE_MS = 5 * 60_000;
const DAY_MS = 86_400_000;

function currencyCode(preferences) {
  const value = preferences?.currency;
  const code =
    typeof value === 'string'
      ? value
      : typeof value?.code === 'string'
        ? value.code
        : null;

  return code && /^[A-Z]{3}$/.test(code) ? code : null;
}

export function validateTimeZone(timeZone) {
  try {
    new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date(0));
  } catch {
    throw new Error('LOCAL_TIME_ZONE must be a valid IANA time zone');
  }
}

function dateFormatter(timeZone) {
  validateTimeZone(timeZone);
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function formattedDate(timestamp, formatter) {
  const parts = Object.fromEntries(
    formatter
      .formatToParts(new Date(timestamp))
      .filter(({ type }) => type !== 'literal')
      .map(({ type, value }) => [type, value]),
  );
  const year = Number(parts.year);
  const month = Number(parts.month);
  const day = Number(parts.day);
  return {
    label: `${parts.year}-${parts.month}-${parts.day}`,
    ordinal: Date.UTC(year, month - 1, day),
  };
}

function reconciliationRecord(lastReconciled, formatter) {
  if (typeof lastReconciled !== 'string') return null;

  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(lastReconciled);
  if (dateOnly) {
    const year = Number(dateOnly[1]);
    const month = Number(dateOnly[2]);
    const day = Number(dateOnly[3]);
    const ordinal = Date.UTC(year, month - 1, day);
    const parsed = new Date(ordinal);
    if (
      parsed.getUTCFullYear() !== year ||
      parsed.getUTCMonth() !== month - 1 ||
      parsed.getUTCDate() !== day
    ) {
      return null;
    }
    return { label: lastReconciled, ordinal, timestamp: ordinal };
  }

  const timestamp = /^\d+$/.test(lastReconciled)
    ? Number(lastReconciled)
    : Date.parse(lastReconciled);
  if (!Number.isSafeInteger(timestamp)) return null;
  return { ...formattedDate(timestamp, formatter), timestamp };
}

function reconciliationSummary(accounts, now, timeZone) {
  const formatter = dateFormatter(timeZone);
  const reconciled = accounts
    .filter(
      (account) =>
        !account.closed &&
        typeof account.name === 'string' &&
        typeof account.last_reconciled === 'string',
    )
    .map((account) => {
      const record = reconciliationRecord(account.last_reconciled, formatter);
      return record === null
        ? null
        : {
            accountName: account.name,
            on: record.label,
            ordinal: record.ordinal,
            timestamp: record.timestamp,
          };
    })
    .filter(Boolean)
    .sort((left, right) => left.timestamp - right.timestamp);
  const oldest = reconciled[0];
  const today = formattedDate(now.getTime(), formatter).ordinal;

  return {
    oldestReconciledAccountName: oldest?.accountName ?? null,
    oldestReconciledOn: oldest?.on ?? null,
    oldestReconciledDaysAgo: oldest
      ? Math.max(0, Math.round((today - oldest.ordinal) / DAY_MS))
      : null,
  };
}

export async function collectSummary(actual, now = () => new Date(), timeZone = 'UTC') {
  const [accounts, preferences, reconciliationResult] = await Promise.all([
    actual.getAccounts(),
    actual.getPreferences(),
    actual.aqlQuery(actual.q('accounts').select(['name', 'closed', 'last_reconciled'])),
  ]);
  const collectedAt = now();
  let netWorthCents = 0;

  for (const account of accounts) {
    if (!account.closed) {
      netWorthCents += await actual.getAccountBalance(account.id);
    }
  }

  return {
    netWorthCents,
    currency: currencyCode(preferences),
    ...reconciliationSummary(reconciliationResult.data, collectedAt, timeZone),
    asOf: collectedAt.toISOString(),
  };
}

export class SummaryCache {
  #summary;
  #refresh;
  #retryAt = 0;

  constructor({ load, now = () => Date.now(), cacheMs = DISPLAY_CACHE_MS, retryMs = 60_000 }) {
    this.load = load;
    this.now = now;
    this.cacheMs = cacheMs;
    this.retryMs = retryMs;
  }

  async get() {
    const current = this.now();
    if (this.#summary && current - Date.parse(this.#summary.asOf) < this.cacheMs) {
      return { ...this.#summary, stale: false };
    }
    if (this.#summary && current < this.#retryAt) {
      return { ...this.#summary, stale: true };
    }
    if (!this.#refresh) {
      this.#refresh = this.load()
        .then((summary) => {
          this.#summary = summary;
          this.#retryAt = 0;
          return summary;
        })
        .catch((error) => {
          this.#retryAt = this.now() + this.retryMs;
          throw error;
        })
        .finally(() => {
          this.#refresh = undefined;
        });
    }

    try {
      return { ...(await this.#refresh), stale: false };
    } catch (error) {
      if (this.#summary) {
        return { ...this.#summary, stale: true };
      }
      throw error;
    }
  }
}

export function normalizeWeather(current, daily) {
  const weatherCode = Number(current?.weather_code);
  const temperatureC = Number(current?.temperature_2m);
  const isDayValue = Number(current?.is_day);

  if (
    !Number.isInteger(weatherCode) ||
    !Number.isFinite(temperatureC) ||
    (isDayValue !== 0 && isDayValue !== 1)
  ) {
    throw new Error('weather response is missing current conditions');
  }

  const sunriseSeconds = Number(daily?.sunrise?.[0]);
  const sunsetSeconds = Number(daily?.sunset?.[0]);
  if (
    !Number.isSafeInteger(sunriseSeconds) ||
    !Number.isSafeInteger(sunsetSeconds) ||
    sunriseSeconds >= sunsetSeconds
  ) {
    throw new Error('weather response is missing sunrise or sunset');
  }

  let condition = 'unknown';
  let label = 'WEATHER';
  if (weatherCode === 0) {
    condition = 'clear';
    label = 'CLEAR';
  } else if (weatherCode === 1) {
    condition = 'cloudy';
    label = 'MOSTLY CLEAR';
  } else if (weatherCode === 2) {
    condition = 'cloudy';
    label = 'PARTLY CLOUDY';
  } else if (weatherCode === 3) {
    condition = 'cloudy';
    label = 'OVERCAST';
  } else if (weatherCode === 45 || weatherCode === 48) {
    condition = 'fog';
    label = 'FOGGY';
  } else if (
    (weatherCode >= 51 && weatherCode <= 67) ||
    (weatherCode >= 80 && weatherCode <= 82)
  ) {
    condition = 'rain';
    label = weatherCode <= 57 ? 'DRIZZLE' : 'RAIN';
  } else if (
    (weatherCode >= 71 && weatherCode <= 77) ||
    (weatherCode >= 85 && weatherCode <= 86)
  ) {
    condition = 'snow';
    label = 'SNOW';
  } else if (weatherCode >= 95 && weatherCode <= 99) {
    condition = 'storm';
    label = 'THUNDERSTORM';
  }

  return {
    condition,
    label,
    weatherCode,
    isDay: isDayValue === 1,
    temperatureC: Math.round(temperatureC),
    observedAt: typeof current.time === 'number' && Number.isSafeInteger(current.time)
      ? new Date(current.time * 1000).toISOString()
      : typeof current.time === 'string'
        ? current.time
        : null,
    sunriseAt: new Date(sunriseSeconds * 1000).toISOString(),
    sunsetAt: new Date(sunsetSeconds * 1000).toISOString(),
  };
}

function smoothstep(start, end, value) {
  const position = Math.max(0, Math.min(1, (value - start) / (end - start)));
  return position * position * (3 - (2 * position));
}

function localClock(timestamp, timeZone) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone,
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    })
      .formatToParts(new Date(timestamp))
      .filter(({ type }) => type !== 'literal')
      .map(({ type, value }) => [type, value]),
  );
  return {
    time: `${parts.hour}:${parts.minute}`,
    period: parts.dayPeriod,
    label: `${parts.hour}:${parts.minute} ${parts.dayPeriod}`,
  };
}

export function themeForTime(weather, now = new Date(), timeZone = 'UTC') {
  validateTimeZone(timeZone);
  const current = now.getTime();
  const sunrise = Date.parse(weather?.sunriseAt);
  const sunset = Date.parse(weather?.sunsetAt);
  if (!Number.isFinite(sunrise) || !Number.isFinite(sunset) || sunrise >= sunset) {
    throw new Error('weather theme requires valid sunrise and sunset times');
  }

  const hour = 60 * 60_000;
  let darkness;
  if (current < sunrise - hour || current >= sunset + (75 * 60_000)) {
    darkness = 1;
  } else if (current < sunrise + hour) {
    darkness = 1 - smoothstep(sunrise - hour, sunrise + hour, current);
  } else if (current < sunset - (75 * 60_000)) {
    darkness = 0;
  } else {
    darkness = smoothstep(sunset - (75 * 60_000), sunset + (75 * 60_000), current);
  }

  const local = localClock(current, timeZone);
  return {
    localTime: local.time,
    localPeriod: local.period,
    sunrise: localClock(sunrise, timeZone).label,
    sunset: localClock(sunset, timeZone).label,
    darknessPercent: Math.round(darkness * 100),
  };
}

export class WeatherCache {
  #weather;
  #refresh;
  #retryAt = 0;
  #expiresAt = 0;
  #lastError;

  constructor({ load, now = () => Date.now(), cacheMs = WEATHER_CACHE_MS, retryMs = 60_000 }) {
    this.load = load;
    this.now = now;
    this.cacheMs = cacheMs;
    this.retryMs = retryMs;
  }

  async get() {
    const current = this.now();
    if (this.#weather && current < this.#expiresAt) {
      return { ...this.#weather, stale: false };
    }
    if (current < this.#retryAt) {
      if (this.#weather) return { ...this.#weather, stale: true };
      throw this.#lastError;
    }
    if (!this.#refresh) {
      this.#refresh = this.load()
        .then((weather) => {
          this.#weather = weather;
          this.#expiresAt = this.now() + this.cacheMs;
          this.#retryAt = 0;
          this.#lastError = undefined;
          return weather;
        })
        .catch((error) => {
          this.#retryAt = this.now() + this.retryMs;
          this.#lastError = error;
          throw error;
        })
        .finally(() => {
          this.#refresh = undefined;
        });
    }

    try {
      return { ...(await this.#refresh), stale: false };
    } catch (error) {
      if (this.#weather) return { ...this.#weather, stale: true };
      throw error;
    }
  }
}

export class FocusState {
  #enabled = false;
  #updatedAt = null;
  #statePath;

  constructor({ now = () => new Date(), statePath } = {}) {
    this.now = now;
    this.#statePath = statePath;
    if (statePath) this.#restore();
  }

  #restore() {
    let stored;
    try {
      stored = JSON.parse(readFileSync(this.#statePath, 'utf8'));
    } catch (error) {
      if (error?.code === 'ENOENT') return;
      throw new Error(`unable to load Focus Mode state: ${error.message}`, { cause: error });
    }

    if (typeof stored?.focusMode !== 'boolean' || typeof stored.focusUpdatedAt !== 'string') {
      throw new Error('Focus Mode state is invalid');
    }
    this.#enabled = stored.focusMode;
    this.#updatedAt = stored.focusUpdatedAt;
  }

  #persist(snapshot) {
    if (!this.#statePath) return;

    const temporaryPath = `${this.#statePath}.next`;
    writeFileSync(temporaryPath, JSON.stringify(snapshot), { encoding: 'utf8', mode: 0o600 });
    renameSync(temporaryPath, this.#statePath);
  }

  set(enabled) {
    if (typeof enabled !== 'boolean') {
      throw new TypeError('focusMode must be a boolean');
    }

    const snapshot = {
      focusMode: enabled,
      focusUpdatedAt: this.now().toISOString(),
    };
    this.#persist(snapshot);
    this.#enabled = snapshot.focusMode;
    this.#updatedAt = snapshot.focusUpdatedAt;
    return snapshot;
  }

  snapshot() {
    return {
      focusMode: this.#enabled,
      focusUpdatedAt: this.#updatedAt,
    };
  }
}

export function validBearer(authorization, expectedToken) {
  return authorization === `Bearer ${expectedToken}`;
}
