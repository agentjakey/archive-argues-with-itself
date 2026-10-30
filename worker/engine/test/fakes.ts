// A small in-memory stand-in for the D1 statements the Worker runs, and an Env built around it.
import type { Env } from "../src/config";

type Row = Record<string, string | number | null>;

export class FakeD1 {
  answers = new Map<string, Row>();
  budget = new Map<string, number>();

  prepare(sql: string) {
    const db = this;
    let params: unknown[] = [];
    const statement = {
      bind(...values: unknown[]) {
        params = values;
        return statement;
      },
      async first<T>(): Promise<T | null> {
        if (sql.startsWith("SELECT") && sql.includes("FROM answers_v2")) {
          const [key, now] = params as [string, string];
          const row = db.answers.get(key);
          if (!row || (row.expires_at !== null && String(row.expires_at) < now)) return null;
          return { ...row } as T;
        }
        if (sql.startsWith("INSERT INTO model_budget")) {
          const [day] = params as [string];
          const calls = (db.budget.get(day) ?? 0) + 1;
          db.budget.set(day, calls);
          return { calls } as T;
        }
        throw new Error(`FakeD1 does not know: ${sql}`);
      },
      async run() {
        if (sql.startsWith("INSERT OR REPLACE INTO answers_v2")) {
          const columns = sql.slice(sql.indexOf("(") + 1, sql.indexOf(")")).split(",").map((c) => c.trim());
          const row: Row = {};
          columns.forEach((c, i) => (row[c] = params[i] as string | number | null));
          db.answers.set(String(row.key), row);
          return { meta: { changes: 1 } };
        }
        if (sql.startsWith("DELETE FROM answers_v2")) {
          const [now] = params as [string];
          let changes = 0;
          for (const [key, row] of db.answers) {
            if (row.expires_at !== null && String(row.expires_at) < now) {
              db.answers.delete(key);
              changes += 1;
            }
          }
          return { meta: { changes } };
        }
        throw new Error(`FakeD1 does not know: ${sql}`);
      },
    };
    return statement;
  }
}

export function fakeEnv(overrides: Partial<Env> = {}): Env {
  return {
    DB: new FakeD1() as unknown as D1Database,
    RELEASE_ID: "test-release",
    ENGINE_LAYOUT: "single",
    INSTANCE_TYPE: "standard-3",
    INSTANCE_TYPE_PILOT: "",
    INSTANCE_TYPE_MICROLOG: "",
    SLEEP_AFTER_MINUTES: "15",
    PROVISION_MODE: "r2-binding",
    DENSE_BACKEND: "numpy",
    ALLOWED_ORIGINS: "https://archiveargues.org",
    DAILY_MODEL_CALLS: "2",
    TURNSTILE_REQUIRED: "true",
    KEEP_WARM_WINDOWS: "",
    PUBLIC_URL: "https://archiveargues.org",
    ...overrides,
  } as Env;
}
