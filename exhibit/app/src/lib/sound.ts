// The dial's click: a short tick made in the browser (no audio file), a little brighter on each
// decade. Sound is off until the visitor turns it on, and every sound has a visible twin on screen.
type AudioContextClass = typeof AudioContext;

let context: AudioContext | null = null;

function audioClass(): AudioContextClass | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { AudioContext?: AudioContextClass; webkitAudioContext?: AudioContextClass };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
}

export function tick(decade: boolean): void {
  const Audio = audioClass();
  if (!Audio) return;
  try {
    context = context ?? new Audio();
    const now = context.currentTime;
    const osc = context.createOscillator();
    const gain = context.createGain();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(decade ? 1320 : 880, now);
    gain.gain.setValueAtTime(decade ? 0.08 : 0.05, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.04);
    osc.connect(gain);
    gain.connect(context.destination);
    osc.start(now);
    osc.stop(now + 0.05);
  } catch {
    // No audio device: the dial still works and still shows every step.
  }
}
