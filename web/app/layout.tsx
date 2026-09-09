import type { ReactNode } from "react";

export const metadata = {
  title: "The Archive Argues With Itself",
  description:
    "A civic memory debugger for Canada's public record: page-level provenance, temporal comparison, and visible archival uncertainty.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
