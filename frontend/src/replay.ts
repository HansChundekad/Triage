import type { StreamEvent } from "./types";

const STEP_DELAY_MS = 700;   // base cadence between events
const MAX_GAP_MS = 1500;     // cap, so replay never stalls

export function startReplay(
  events: StreamEvent[],
  onEvent: (e: StreamEvent) => void,
  opts: { speed?: number } = {}
): () => void {
  const speed = opts.speed ?? 1;
  let i = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let cancelled = false;

  const tick = () => {
    if (cancelled || i >= events.length) return;
    onEvent(events[i]);
    i += 1;
    if (i < events.length) {
      const delay = Math.min(STEP_DELAY_MS, MAX_GAP_MS) / speed;
      timer = setTimeout(tick, delay);
    }
  };
  timer = setTimeout(tick, STEP_DELAY_MS / speed);

  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}
