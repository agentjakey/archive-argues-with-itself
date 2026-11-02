// The three Node functions vite.config.ts uses to publish design/tokens.css and its fonts, typed here
// so the site does not need the full Node type package.
declare module "node:fs" {
  export function readFileSync(path: string): Uint8Array;
  export function readdirSync(path: string): string[];
}
declare module "node:url" {
  export function fileURLToPath(url: URL | string): string;
}
