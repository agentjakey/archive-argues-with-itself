// A real QR code to the live site, as a static inline SVG (no runtime library, CSP-safe,
// works offline). Generated once at build time with segno from the BASE url only (no query
// params), so it always resolves to a clean home state. To regenerate after a URL change:
//   python -c "import segno; qr=segno.make('<URL>', error='m'); m=qr.matrix; b=4; \
//     print(''.join(f'M{c+b} {r+b}h1v1h-1z' for r,row in enumerate(m) for c,v in enumerate(row) if v))"
// and update QR_SIZE to len(matrix)+2*b.
const QR_SIZE = 33;
const QR_PATH =
  "M4 4h1v1h-1zM5 4h1v1h-1zM6 4h1v1h-1zM7 4h1v1h-1zM8 4h1v1h-1zM9 4h1v1h-1zM10 4h1v1h-1zM12 4h1v1h-1zM14 4h1v1h-1zM17 4h1v1h-1zM18 4h1v1h-1zM22 4h1v1h-1zM23 4h1v1h-1zM24 4h1v1h-1zM25 4h1v1h-1zM26 4h1v1h-1zM27 4h1v1h-1zM28 4h1v1h-1zM4 5h1v1h-1zM10 5h1v1h-1zM12 5h1v1h-1zM14 5h1v1h-1zM16 5h1v1h-1zM22 5h1v1h-1zM28 5h1v1h-1zM4 6h1v1h-1zM6 6h1v1h-1zM7 6h1v1h-1zM8 6h1v1h-1zM10 6h1v1h-1zM12 6h1v1h-1zM13 6h1v1h-1zM14 6h1v1h-1zM15 6h1v1h-1zM17 6h1v1h-1zM18 6h1v1h-1zM20 6h1v1h-1zM22 6h1v1h-1zM24 6h1v1h-1zM25 6h1v1h-1zM26 6h1v1h-1zM28 6h1v1h-1zM4 7h1v1h-1zM6 7h1v1h-1zM7 7h1v1h-1zM8 7h1v1h-1zM10 7h1v1h-1zM16 7h1v1h-1zM17 7h1v1h-1zM22 7h1v1h-1zM24 7h1v1h-1zM25 7h1v1h-1zM26 7h1v1h-1zM28 7h1v1h-1zM4 8h1v1h-1zM6 8h1v1h-1zM7 8h1v1h-1zM8 8h1v1h-1zM10 8h1v1h-1zM12 8h1v1h-1zM13 8h1v1h-1zM14 8h1v1h-1zM15 8h1v1h-1zM16 8h1v1h-1zM20 8h1v1h-1zM22 8h1v1h-1zM24 8h1v1h-1zM25 8h1v1h-1zM26 8h1v1h-1zM28 8h1v1h-1zM4 9h1v1h-1zM10 9h1v1h-1zM14 9h1v1h-1zM15 9h1v1h-1zM16 9h1v1h-1zM18 9h1v1h-1zM22 9h1v1h-1zM28 9h1v1h-1zM4 10h1v1h-1zM5 10h1v1h-1zM6 10h1v1h-1zM7 10h1v1h-1zM8 10h1v1h-1zM9 10h1v1h-1zM10 10h1v1h-1zM12 10h1v1h-1zM14 10h1v1h-1zM16 10h1v1h-1zM18 10h1v1h-1zM20 10h1v1h-1zM22 10h1v1h-1zM23 10h1v1h-1zM24 10h1v1h-1zM25 10h1v1h-1zM26 10h1v1h-1zM27 10h1v1h-1zM28 10h1v1h-1zM13 11h1v1h-1zM14 11h1v1h-1zM16 11h1v1h-1zM17 11h1v1h-1zM4 12h1v1h-1zM7 12h1v1h-1zM8 12h1v1h-1zM9 12h1v1h-1zM10 12h1v1h-1zM11 12h1v1h-1zM12 12h1v1h-1zM13 12h1v1h-1zM16 12h1v1h-1zM18 12h1v1h-1zM19 12h1v1h-1zM20 12h1v1h-1zM21 12h1v1h-1zM24 12h1v1h-1zM26 12h1v1h-1zM27 12h1v1h-1zM28 12h1v1h-1zM5 13h1v1h-1zM6 13h1v1h-1zM8 13h1v1h-1zM11 13h1v1h-1zM12 13h1v1h-1zM15 13h1v1h-1zM18 13h1v1h-1zM19 13h1v1h-1zM21 13h1v1h-1zM23 13h1v1h-1zM24 13h1v1h-1zM25 13h1v1h-1zM26 13h1v1h-1zM27 13h1v1h-1zM8 14h1v1h-1zM9 14h1v1h-1zM10 14h1v1h-1zM11 14h1v1h-1zM14 14h1v1h-1zM19 14h1v1h-1zM20 14h1v1h-1zM21 14h1v1h-1zM22 14h1v1h-1zM23 14h1v1h-1zM24 14h1v1h-1zM25 14h1v1h-1zM28 14h1v1h-1zM4 15h1v1h-1zM8 15h1v1h-1zM11 15h1v1h-1zM12 15h1v1h-1zM15 15h1v1h-1zM18 15h1v1h-1zM21 15h1v1h-1zM25 15h1v1h-1zM26 15h1v1h-1zM27 15h1v1h-1zM28 15h1v1h-1zM4 16h1v1h-1zM7 16h1v1h-1zM9 16h1v1h-1zM10 16h1v1h-1zM14 16h1v1h-1zM15 16h1v1h-1zM16 16h1v1h-1zM19 16h1v1h-1zM20 16h1v1h-1zM22 16h1v1h-1zM23 16h1v1h-1zM28 16h1v1h-1zM4 17h1v1h-1zM7 17h1v1h-1zM8 17h1v1h-1zM12 17h1v1h-1zM13 17h1v1h-1zM16 17h1v1h-1zM17 17h1v1h-1zM19 17h1v1h-1zM20 17h1v1h-1zM24 17h1v1h-1zM27 17h1v1h-1zM4 18h1v1h-1zM5 18h1v1h-1zM7 18h1v1h-1zM9 18h1v1h-1zM10 18h1v1h-1zM11 18h1v1h-1zM12 18h1v1h-1zM16 18h1v1h-1zM19 18h1v1h-1zM20 18h1v1h-1zM22 18h1v1h-1zM24 18h1v1h-1zM25 18h1v1h-1zM26 18h1v1h-1zM27 18h1v1h-1zM28 18h1v1h-1zM4 19h1v1h-1zM6 19h1v1h-1zM8 19h1v1h-1zM12 19h1v1h-1zM16 19h1v1h-1zM19 19h1v1h-1zM21 19h1v1h-1zM23 19h1v1h-1zM25 19h1v1h-1zM26 19h1v1h-1zM28 19h1v1h-1zM4 20h1v1h-1zM6 20h1v1h-1zM8 20h1v1h-1zM10 20h1v1h-1zM15 20h1v1h-1zM16 20h1v1h-1zM17 20h1v1h-1zM18 20h1v1h-1zM19 20h1v1h-1zM20 20h1v1h-1zM21 20h1v1h-1zM22 20h1v1h-1zM23 20h1v1h-1zM24 20h1v1h-1zM26 20h1v1h-1zM27 20h1v1h-1zM12 21h1v1h-1zM14 21h1v1h-1zM15 21h1v1h-1zM16 21h1v1h-1zM17 21h1v1h-1zM19 21h1v1h-1zM20 21h1v1h-1zM24 21h1v1h-1zM26 21h1v1h-1zM27 21h1v1h-1zM4 22h1v1h-1zM5 22h1v1h-1zM6 22h1v1h-1zM7 22h1v1h-1zM8 22h1v1h-1zM9 22h1v1h-1zM10 22h1v1h-1zM12 22h1v1h-1zM15 22h1v1h-1zM20 22h1v1h-1zM22 22h1v1h-1zM24 22h1v1h-1zM28 22h1v1h-1zM4 23h1v1h-1zM10 23h1v1h-1zM12 23h1v1h-1zM15 23h1v1h-1zM17 23h1v1h-1zM18 23h1v1h-1zM19 23h1v1h-1zM20 23h1v1h-1zM24 23h1v1h-1zM27 23h1v1h-1zM28 23h1v1h-1zM4 24h1v1h-1zM6 24h1v1h-1zM7 24h1v1h-1zM8 24h1v1h-1zM10 24h1v1h-1zM12 24h1v1h-1zM13 24h1v1h-1zM16 24h1v1h-1zM18 24h1v1h-1zM19 24h1v1h-1zM20 24h1v1h-1zM21 24h1v1h-1zM22 24h1v1h-1zM23 24h1v1h-1zM24 24h1v1h-1zM4 25h1v1h-1zM6 25h1v1h-1zM7 25h1v1h-1zM8 25h1v1h-1zM10 25h1v1h-1zM12 25h1v1h-1zM13 25h1v1h-1zM15 25h1v1h-1zM17 25h1v1h-1zM18 25h1v1h-1zM19 25h1v1h-1zM20 25h1v1h-1zM21 25h1v1h-1zM22 25h1v1h-1zM27 25h1v1h-1zM28 25h1v1h-1zM4 26h1v1h-1zM6 26h1v1h-1zM7 26h1v1h-1zM8 26h1v1h-1zM10 26h1v1h-1zM13 26h1v1h-1zM14 26h1v1h-1zM15 26h1v1h-1zM16 26h1v1h-1zM17 26h1v1h-1zM19 26h1v1h-1zM20 26h1v1h-1zM21 26h1v1h-1zM24 26h1v1h-1zM25 26h1v1h-1zM26 26h1v1h-1zM27 26h1v1h-1zM28 26h1v1h-1zM4 27h1v1h-1zM10 27h1v1h-1zM16 27h1v1h-1zM18 27h1v1h-1zM21 27h1v1h-1zM23 27h1v1h-1zM24 27h1v1h-1zM26 27h1v1h-1zM27 27h1v1h-1zM28 27h1v1h-1zM4 28h1v1h-1zM5 28h1v1h-1zM6 28h1v1h-1zM7 28h1v1h-1zM8 28h1v1h-1zM9 28h1v1h-1zM10 28h1v1h-1zM12 28h1v1h-1zM13 28h1v1h-1zM15 28h1v1h-1zM20 28h1v1h-1zM21 28h1v1h-1zM22 28h1v1h-1zM25 28h1v1h-1zM28 28h1v1h-1z";

/** Kiosk-only: a scannable QR to the live site's clean home, so a visitor can take it with
 *  them. Static SVG, no library, no network. */
export function KioskQr() {
  return (
    <div className="shrink-0 text-center text-xs text-muted">
      <svg
        viewBox={`0 0 ${QR_SIZE} ${QR_SIZE}`}
        width="96"
        height="96"
        role="img"
        aria-label="QR code to the live site"
        className="border border-rule"
        shapeRendering="crispEdges"
      >
        <rect width={QR_SIZE} height={QR_SIZE} fill="#ffffff" />
        <path d={QR_PATH} fill="#000000" />
      </svg>
      <p className="mt-1">Take it with you</p>
    </div>
  );
}
