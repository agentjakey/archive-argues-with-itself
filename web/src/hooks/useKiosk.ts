import { useEffect, useMemo } from "react";

/** ?kiosk=1 enlarges type (body.kiosk), hides the filter selects, and shows the
 *  QR placeholder. Read once from the URL. */
export function readKioskFlag(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get("kiosk") === "1";
}

export function useKiosk(): boolean {
  const kiosk = useMemo(() => readKioskFlag(), []);
  useEffect(() => {
    document.body.classList.toggle("kiosk", kiosk);
    return () => document.body.classList.remove("kiosk");
  }, [kiosk]);
  return kiosk;
}
