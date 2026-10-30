// The engine container, run by a Durable Object under the durable_object scheduling policy
// (public beta since 2026-09-30; docs/SELF_HOSTING.md, "Design choices"). The
// Durable Object starts the container on demand, gives it its secrets and its two private routes
// (R2 reads and the answer cache, through Worker entrypoints, so the container holds no R2 key),
// lets it sleep after SLEEP_AFTER_MINUTES of inactivity, and records how long every wake took.
import { DurableObject, WorkerEntrypoint } from "cloudflare:workers";
import { readRow, writeRow, isKey, type CacheRow } from "./cache";
import { ENGINE_CONFIG, type Env, verifyPolicy, whole } from "./config";
import { parseRange } from "./ranges";

const PORT = 8080;
const PROBE_TIMEOUT_MS = 2000;
const PROBE_EVERY_MS = 1000;
const WAKE_LOG_KEY = "wakes";
const WAKE_LOG_LIMIT = 50;
export const R2_HOST = "r2.internal";
export const CACHE_HOST = "cache.internal";

export type Stage = Record<string, string | number | null>;
export type EngineState = "asleep" | "waking" | "ready" | "failed";

export interface WakeRecord {
  release: string;
  name: string;
  mode: string;
  instance: string;
  started_at: string;
  port_open_seconds: number | null;
  ready_seconds: number | null;
  provision: Stage | null;
  exit: string | null;
}

export interface EngineStatus {
  name: string;
  status: EngineState;
  stage: Stage | null;
  error: string | null;
  wake: WakeRecord | null;
}

function instanceOption(value: string): ContainerStartupOptions["instance"] {
  const text = (value || "standard-3").trim();
  if (text.startsWith("{")) {
    const parsed = JSON.parse(text) as { vcpu: number; memoryMib: number; diskMb: number };
    return { vcpu: parsed.vcpu, memoryMib: parsed.memoryMib, diskMb: parsed.diskMb };
  }
  return text as ContainerStartupOptions["instance"];
}

function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export class EngineContainer extends DurableObject<Env> {
  private cacheToken = "";
  private wake: WakeRecord | null = null;
  private startedMs = 0;
  private ready = false;
  private lastStage: Stage | null = null;
  private lastError: string | null = null;

  /** Which engine this is: "engine" (both scopes) or a scope name (split layout). */
  private get engineName(): string {
    return this.ctx.id.name ?? "engine";
  }

  private get container(): Container {
    if (!this.ctx.container) throw new Error("this Durable Object has no container configured");
    return this.ctx.container;
  }

  private instanceSetting(): string {
    if (this.engineName === "pilot") return this.env.INSTANCE_TYPE_PILOT || this.env.INSTANCE_TYPE;
    if (this.engineName === "microlog") return this.env.INSTANCE_TYPE_MICROLOG || this.env.INSTANCE_TYPE;
    return this.env.INSTANCE_TYPE;
  }

  private containerEnv(restoredFromSnapshot: boolean): Record<string, string> {
    const mode = this.env.PROVISION_MODE || "r2-binding";
    const present = mode === "image" || restoredFromSnapshot;
    const env: Record<string, string> = {
      PORT: String(PORT),
      CIVIC_RELEASE_ID: this.env.RELEASE_ID,
      CIVIC_PROVISION: present ? "present" : "r2-binding",
      CIVIC_VERIFY_PRESENT: verifyPolicy(mode, restoredFromSnapshot, this.env.SNAPSHOT_VERIFY),
      CIVIC_R2_PROXY_URL: `http://${R2_HOST}`,
      CIVIC_CACHE_URL: `http://${CACHE_HOST}`,
      CIVIC_CACHE_TOKEN: this.cacheToken,
      CIVIC_DENSE_BACKEND: this.env.DENSE_BACKEND || "numpy",
      PUBLIC_URL: this.env.PUBLIC_URL,
    };
    if (this.engineName === "engine") {
      env.CIVIC_ENABLED_SCOPES = Object.keys(ENGINE_CONFIG.scopes).join(",");
    } else {
      env.CIVIC_SCOPE = this.engineName;
      env.CIVIC_ENABLED_SCOPES = this.engineName;
    }
    if (this.env.ANTHROPIC_API_KEY) env.ANTHROPIC_API_KEY = this.env.ANTHROPIC_API_KEY;
    return env;
  }

  /** Start the container when it is not running. Returns at once; readiness is probed by alarm. */
  private async ensureStarted(): Promise<void> {
    if (this.container.running) return;
    const mode = this.env.PROVISION_MODE || "r2-binding";
    const snapshotId =
      mode === "snapshot" ? await this.ctx.storage.get<string>(`snapshot:${this.env.RELEASE_ID}:${this.engineName}`) : undefined;
    this.cacheToken = randomToken();
    this.ready = false;
    this.lastStage = null;
    this.lastError = null;
    this.startedMs = Date.now();
    const instance = this.instanceSetting();
    const common = { instance: instanceOption(instance), enableInternet: true, env: this.containerEnv(Boolean(snapshotId)) };
    const image = mode === "image" ? this.container.images.baked : this.container.images.base;
    if (snapshotId) {
      this.container.start({ ...common, containerSnapshot: { id: snapshotId } });
    } else {
      if (!image) throw new Error(`no container image for provision mode ${mode}`);
      this.container.start({ ...common, image });
    }
    await this.container.interceptOutboundHttp(R2_HOST, this.ctx.exports.R2Proxy({ props: {} }));
    await this.container.interceptOutboundHttp(CACHE_HOST, this.ctx.exports.CacheProxy({ props: { token: this.cacheToken } }));
    await this.container.setInactivityTimeout(whole(this.env.SLEEP_AFTER_MINUTES, 15) * 60 * 1000);
    this.wake = {
      release: this.env.RELEASE_ID,
      name: this.engineName,
      mode: snapshotId ? "snapshot-restore" : mode,
      instance,
      started_at: new Date(this.startedMs).toISOString(),
      port_open_seconds: null,
      ready_seconds: null,
      provision: null,
      exit: null,
    };
    this.ctx.waitUntil(
      this.container
        .monitor()
        .then(() => this.recordExit("stopped"))
        .catch((err: unknown) => this.recordExit(`exited: ${String((err as Error)?.message ?? err)}`)),
    );
    await this.ctx.storage.setAlarm(Date.now() + PROBE_EVERY_MS);
  }

  private async recordExit(reason: string): Promise<void> {
    this.ready = false;
    if (this.wake) {
      this.wake.exit = reason;
      await this.saveWake();
    }
  }

  private async saveWake(): Promise<void> {
    if (!this.wake) return;
    const log = (await this.ctx.storage.get<WakeRecord[]>(WAKE_LOG_KEY)) ?? [];
    const others = log.filter((w) => w.started_at !== this.wake?.started_at);
    await this.ctx.storage.put(WAKE_LOG_KEY, [...others, { ...this.wake }].slice(-WAKE_LOG_LIMIT));
  }

  /** Ask the engine's /health. null when the port does not answer yet. */
  private async probe(): Promise<{ status: number; body: Record<string, any> } | null> {
    try {
      const resp = await this.container
        .getTcpPort(PORT)
        .fetch(`http://container/health`, { signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
      return { status: resp.status, body: (await resp.json()) as Record<string, any> };
    } catch {
      return null;
    }
  }

  /** Probe once, and keep the wake record and the ready flag current. */
  private async refresh(): Promise<void> {
    if (!this.container.running) {
      this.ready = false;
      return;
    }
    const seen = await this.probe();
    if (!seen) return;
    const elapsed = (Date.now() - this.startedMs) / 1000;
    if (this.wake && this.wake.port_open_seconds === null) this.wake.port_open_seconds = Math.round(elapsed * 10) / 10;
    this.lastStage = (seen.body.stage as Stage) ?? null;
    this.lastError = (seen.body.error as string) ?? null;
    if (seen.status === 200 && !this.ready) {
      this.ready = true;
      if (this.wake) {
        this.wake.ready_seconds = Math.round(elapsed * 10) / 10;
        this.wake.provision = this.lastStage;
        await this.saveWake();
      }
      await this.maybeSnapshot();
    }
  }

  /** In snapshot mode, the first ready container of a release is snapshotted (its disk holds the
   *  verified data), and later wakes restore from it instead of downloading. */
  private async maybeSnapshot(): Promise<void> {
    if ((this.env.PROVISION_MODE || "") !== "snapshot") return;
    const key = `snapshot:${this.env.RELEASE_ID}:${this.engineName}`;
    if (await this.ctx.storage.get<string>(key)) return;
    try {
      const snap = await this.container.snapshotContainer({ name: `${this.env.RELEASE_ID}-${this.engineName}` });
      await this.ctx.storage.put(key, snap.id);
      console.log(JSON.stringify({ event: "snapshot", name: this.engineName, bytes: snap.size }));
    } catch (err) {
      console.log(JSON.stringify({ event: "snapshot_failed", name: this.engineName, error: String(err) }));
    }
  }

  async alarm(): Promise<void> {
    await this.refresh();
    if (this.container.running && !this.ready && !(this.lastStage && this.lastStage.stage === "failed")) {
      await this.ctx.storage.setAlarm(Date.now() + PROBE_EVERY_MS);
    }
  }

  private currentStatus(): EngineStatus {
    let status: EngineState = "asleep";
    if (this.container.running) status = this.ready ? "ready" : "waking";
    if (this.lastError || (this.lastStage && this.lastStage.stage === "failed")) status = "failed";
    return { name: this.engineName, status, stage: this.lastStage, error: this.lastError, wake: this.wake };
  }

  /** The engine's state, without waking it. */
  async status(): Promise<EngineStatus> {
    if (this.container.running && !this.ready) await this.refresh();
    return this.currentStatus();
  }

  /** Start the engine if it is asleep (pre-wake), and report its state. */
  async wakeUp(): Promise<EngineStatus> {
    await this.ensureStarted();
    await this.refresh();
    return this.currentStatus();
  }

  async wakeLog(): Promise<WakeRecord[]> {
    return (await this.ctx.storage.get<WakeRecord[]>(WAKE_LOG_KEY)) ?? [];
  }

  /** Forward a request to the engine. With start=false an asleep engine is not woken. While the
   *  engine is waking, answers 503 with its state, so the site can show progress and retry. */
  async forward(request: Request, start: boolean): Promise<Response> {
    if (start) await this.ensureStarted();
    if (!this.ready) await this.refresh();
    if (!this.ready) {
      return Response.json({ ...this.currentStatus(), retry_after_seconds: 3 }, { status: 503, headers: { "retry-after": "3" } });
    }
    const url = new URL(request.url);
    const inner = new Request(`http://container${url.pathname}${url.search}`, request);
    try {
      return await this.container.getTcpPort(PORT).fetch(inner);
    } catch {
      this.ready = false;
      return Response.json({ ...this.currentStatus(), status: "waking", retry_after_seconds: 3 }, { status: 503 });
    }
  }
}

/** R2 reads for the container, through the Worker's binding: HEAD for the size and ranged GETs,
 *  only for the release's own data objects (config/scopes.toml). */
export class R2Proxy extends WorkerEntrypoint<Env> {
  async fetch(request: Request): Promise<Response> {
    const key = decodeURIComponent(new URL(request.url).pathname.replace(/^\/+/, ""));
    if (!ENGINE_CONFIG.r2_keys.includes(key)) return new Response("not a release object", { status: 404 });
    if (request.method === "HEAD") {
      const head = await this.env.DATA.head(key);
      if (!head) return new Response(null, { status: 404 });
      return new Response(null, { headers: { "content-length": String(head.size), etag: head.httpEtag } });
    }
    if (request.method !== "GET") return new Response("method not allowed", { status: 405 });
    const range = parseRange(request.headers.get("range"));
    if (range === "invalid") return new Response("bad range", { status: 416 });
    const object = await this.env.DATA.get(key, range ? { range } : {});
    if (!object) return new Response(null, { status: 404 });
    if (!range) return new Response(object.body, { headers: { "content-length": String(object.size) } });
    const end = range.offset + range.length - 1;
    return new Response(object.body, {
      status: 206,
      headers: { "content-length": String(range.length), "content-range": `bytes ${range.offset}-${end}/${object.size}` },
    });
  }
}

/** The answer cache (D1) for the container: GET and PUT /cache/<key>, with the per-start token. */
export class CacheProxy extends WorkerEntrypoint<Env, { token: string }> {
  async fetch(request: Request): Promise<Response> {
    const token = this.ctx.props.token;
    if (!token || request.headers.get("authorization") !== `Bearer ${token}`) {
      return new Response("forbidden", { status: 403 });
    }
    const match = /^\/cache\/([0-9a-f]{64})$/.exec(new URL(request.url).pathname);
    if (!match || !isKey(match[1])) return new Response("not found", { status: 404 });
    if (request.method === "GET") {
      const row = await readRow(this.env.DB, match[1]);
      return row ? Response.json(row) : new Response("not found", { status: 404 });
    }
    if (request.method === "PUT") {
      const row = (await request.json()) as CacheRow;
      if (row.key !== match[1]) return new Response("key mismatch", { status: 400 });
      try {
        await writeRow(this.env.DB, row);
      } catch (err) {
        return new Response(String((err as Error).message), { status: 400 });
      }
      return new Response(null, { status: 204 });
    }
    return new Response("method not allowed", { status: 405 });
  }
}
