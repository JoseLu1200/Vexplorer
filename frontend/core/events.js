export function createEventLedger(runId) {
  const bySequence = new Map();
  const missing = [];
  let maximum = 0;
  return {
    append(envelope) {
      if (envelope?.run_id !== runId || !Number.isInteger(envelope?.sequence) || envelope.sequence < 1) return false;
      if (bySequence.has(envelope.sequence)) return false;
      if (maximum > 0 && envelope.sequence > maximum + 1) missing.push({ after: maximum, before: envelope.sequence });
      bySequence.set(envelope.sequence, envelope);
      maximum = Math.max(maximum, envelope.sequence);
      return true;
    },
    events: () => [...bySequence.values()].sort((left, right) => left.sequence - right.sequence),
    gaps: () => [...missing],
    lastSequence: () => maximum,
  };
}

export function eventLabel(event) {
  const labels = {
    run_state_changed: "Estado actualizado",
    tool_started: "Inspección iniciada",
    tool_completed: "Inspección completada",
    validation_issue: "Revisión necesaria",
    result_committed: "Resultado guardado",
    run_finished: "Ejecución finalizada",
    provenance: "Procedencia registrada",
    human_review_committed: "Revisión humana registrada",
    estimate_committed: "Estimación guardada",
    library_item_saved: "Revisión guardada en biblioteca",
  };
  return labels[event?.event_type] ?? "Actividad registrada";
}

export function parseEventStream(body) {
  return String(body ?? "").split(/\r?\n\r?\n/).flatMap((block) => {
    const data = block.split(/\r?\n/).find((line) => line.startsWith("data:"));
    if (!data) return [];
    try { return [JSON.parse(data.slice(5).trim())]; } catch { return []; }
  });
}

export function eventTimestamp(event) {
  return event?.timestamp ?? event?.data?.timestamp ?? null;
}
