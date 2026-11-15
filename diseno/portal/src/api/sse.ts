import type { RunEvent } from "./types";

/** Interpreta un bloque text/event-stream (id/event/data separados por línea en blanco). */
export function parseEventStream(text: string): RunEvent[] {
  const events: RunEvent[] = [];
  for (const frame of text.split(/\r?\n\r?\n/)) {
    const dataLines = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());
    if (!dataLines.length) continue;
    try {
      events.push(JSON.parse(dataLines.join("\n")) as RunEvent);
    } catch {
      // Un marco ilegible se ignora; la instantánea GET /runs/{id} sigue siendo la fuente de verdad.
    }
  }
  return events;
}
