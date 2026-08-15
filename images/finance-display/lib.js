export const CENTS_PER_UNIT = 100;
export const DISPLAY_CACHE_MS = 15_000;
export const WEATHER_CACHE_MS = 5 * 60_000;


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

function reconciliationTimestamp(lastReconciled) {
  if (typeof lastReconciled !== 'string') return null;

  const timestamp = /^\d+$/.test(lastReconciled)
    ? Number(lastReconciled)
    : Date.parse(lastReconciled);
  return Number.isSafeInteger(timestamp) ? timestamp : null;
}

function reconciliationSummary(accounts, now) {
  const reconciled = accounts
    .filter(
      (account) =>
        !account.closed &&
        typeof account.name === 'string' &&
        typeof account.last_reconciled === 'string',
    )
    .map((account) => {
      const timestamp = reconciliationTimestamp(account.last_reconciled);
      return timestamp === null
        ? null
        : {
            accountName: account.name,
            on: new Date(timestamp).toISOString().slice(0, 10),
            timestamp,
          };
    })
    .filter(Boolean)
    .sort((left, right) => left.timestamp - right.timestamp);
  const oldest = reconciled[0];

  return {
    oldestReconciledAccountName: oldest?.accountName ?? null,
    oldestReconciledOn: oldest?.on ?? null,
    oldestReconciledDaysAgo: oldest
      ? Math.max(0, Math.floor((now.getTime() - oldest.timestamp) / 86_400_000))
      : null,
  };
}

export async function collectSummary(actual, now = () => new Date()) {
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
    ...reconciliationSummary(reconciliationResult.data, collectedAt),
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

export function normalizeWeather(current) {
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
    observedAt: typeof current.time === 'string' ? current.time : null,
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

  constructor({ now = () => new Date() } = {}) {
    this.now = now;
  }

  set(enabled) {
    if (typeof enabled !== 'boolean') {
      throw new TypeError('focusMode must be a boolean');
    }
    this.#enabled = enabled;
    this.#updatedAt = this.now().toISOString();
    return this.snapshot();
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
