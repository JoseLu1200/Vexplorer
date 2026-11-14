export function createEventLedger(runId) {
  const bySequence = new Map();
  let maximum = 0;
  return {
    append(envelope) {
      if (envelope?.run_id !== runId || !Number.isInteger(envelope?.sequence) || envelope.sequence < 1) return false;
      if (bySequence.has(envelope.sequence)) return false;
      bySequence.set(envelope.sequence, envelope);
      maximum = Math.max(maximum, envelope.sequence);
      return true;
    },
    events: () => [...bySequence.values()].sort((left, right) => left.sequence - right.sequence),
    gaps: () => {
      const sequences = [...bySequence.keys()].sort((left, right) => left - right);
      const prefix = sequences[0] > 1 ? [{ after: 0, before: sequences[0] }] : [];
      return [...prefix, ...sequences.slice(1).flatMap((sequence, index) => sequence > sequences[index] + 1 ? [{ after: sequences[index], before: sequence }] : [])];
    },
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
    table_drawings_committed: "Planos de mesa guardados",
    table_cost_committed: "Costes de mesa guardados",
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
