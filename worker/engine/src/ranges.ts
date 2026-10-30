// The one Range form the container's provisioning sends: "bytes=<first>-<last>", both inclusive.
export function parseRange(header: string | null): { offset: number; length: number } | null | "invalid" {
  if (!header) return null;
  const match = /^bytes=(\d+)-(\d+)$/.exec(header.trim());
  if (!match) return "invalid";
  const start = Number(match[1]);
  const end = Number(match[2]);
  if (end < start) return "invalid";
  return { offset: start, length: end - start + 1 };
}
