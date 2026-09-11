/** Kiosk-only placeholder for the public URL QR code. In flow, in the header. */
export function KioskQr() {
  return (
    <div className="shrink-0 text-center text-xs text-muted" aria-label="QR code placeholder">
      <div className="h-24 w-24 border border-dashed border-rule flex items-center justify-center font-mono">QR</div>
      <p className="mt-1">Public URL</p>
    </div>
  );
}
