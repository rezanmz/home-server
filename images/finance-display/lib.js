export const CENTS_PER_UNIT = 100;
export const DISPLAY_CACHE_MS = 15_000;


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

export function validBearer(authorization, expectedToken) {
  return authorization === `Bearer ${expectedToken}`;
}
