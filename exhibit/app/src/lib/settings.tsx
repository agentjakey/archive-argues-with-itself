// What the visitor switched on for this visit: sound (off by default) and less motion (on when the
// device asks for reduced motion). Held in memory only and reset with the visit.
import { createContext, useContext } from "react";

export type Settings = { sound: boolean; reducedMotion: boolean };

export const SettingsContext = createContext<Settings>({ sound: false, reducedMotion: false });

export function useSettings(): Settings {
  return useContext(SettingsContext);
}
