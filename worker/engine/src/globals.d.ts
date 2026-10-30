// Types ctx.exports (the loopback bindings for this module's own exports) so the Durable Object can
// hand its container the R2Proxy and CacheProxy entrypoints.
declare namespace Cloudflare {
  interface GlobalProps {
    mainModule: typeof import("./index");
    durableNamespaces: "EngineContainer";
  }
}
