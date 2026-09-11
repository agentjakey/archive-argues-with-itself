import { useEffect, useMemo } from "react";

/** ?kiosk=1 enlarges type (body.kiosk), hides the filter selects, shows the QR
 *  placeholder, and runs the attract loop. ?offline=1 additionally hides the ask box,
 *  so an exhibit with no network only offers cached questions and stories. Both are
 *  read once from the URL and preserved by the URL state. */
export function readKioskFlag(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get("kiosk") === "1";
}

export function readOfflineFlag(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get("offline") === "1";
}

export function useKiosk(): boolean {
  const kiosk = useMemo(() => readKioskFlag(), []);
  useEffect(() => {
    document.body.classList.toggle("kiosk", kiosk);
    return () => document.body.classList.remove("kiosk");
  }, [kiosk]);
  return kiosk;
}

export function useOffline(): boolean {
  return useMemo(() => readOfflineFlag(), []);
}
