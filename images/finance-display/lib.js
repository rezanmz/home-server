export const CENTS_PER_UNIT = 100;

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

export async function collectSummary(actual, now = () => new Date()) {
  const [accounts, preferences] = await Promise.all([
    actual.getAccounts(),
    actual.getPreferences(),
  ]);
  let netWorthCents = 0;

  for (const account of accounts) {
    if (!account.closed) {
      netWorthCents += await actual.getAccountBalance(account.id);
    }
  }

  return {
    netWorthCents,
    currency: currencyCode(preferences),
    asOf: now().toISOString(),
  };
}

export class SummaryCache {
  #summary;
  #refresh;
  #retryAt = 0;

  constructor({ load, now = () => Date.now(), cacheMs = 300_000, retryMs = 60_000 }) {
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

export function validBearer(authorization, expectedToken) {
  return authorization === `Bearer ${expectedToken}`;
}
