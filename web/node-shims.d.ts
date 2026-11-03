// The few Node functions vite.config.ts and the file-reading tests use (publishing design/tokens.css
// and its fonts; checking the featured questions against site/data), typed here so the site does not
// need the full Node type package.
declare module "node:fs" {
  export function readFileSync(path: string): Uint8Array;
  export function readFileSync(path: string, encoding: "utf-8"): string;
  export function readdirSync(path: string): string[];
}
declare module "node:url" {
  export function fileURLToPath(url: URL | string): string;
}
declare module "node:path" {
  export function resolve(...parts: string[]): string;
}
declare const process: { cwd(): string };
