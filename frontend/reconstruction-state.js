export function buildRefinement({answers = [], intendedUse = '', envelope = {}}) {
  const result = {
    answers: answers.filter(a => a.answer.trim()).map(a => ({question:a.question, answer:a.answer.trim()})),
    envelope_mm: {},
  };
  if (intendedUse.trim()) result.intended_use = intendedUse.trim();
  for (const key of ['width', 'depth', 'height']) {
    const raw = String(envelope[key] ?? '').trim();
    if (!raw) continue;
    const value = Number(raw);
    if (!Number.isFinite(value) || value <= 0 || value > 100000) {
      throw new Error('Las cotas deben ser números mayores que 0 y hasta 100000 mm.');
    }
    result.envelope_mm[key] = value;
  }
  if (!result.answers.length && !result.intended_use && !Object.keys(result.envelope_mm).length) {
    throw new Error('Añade una respuesta, un uso previsto o una cota para actualizar la propuesta.');
  }
  return result;
}

export function clearProposal($, viewer) {
  viewer?.dispose();
  for (const id of ['assessment','parts','preview','refine-section']) $(id).hidden = true;
  for (const id of ['parts-body','downloads','viewer','partial-download']) $(id).replaceChildren();
  $('preview').removeAttribute('src');
  $('exploded').checked = false;
  $('exploded').disabled = true;
  $('selected').textContent = 'Selecciona una pieza para ver sus medidas.';
}

export function refinementQuestions(state, proposal) {
  const previous = new Map((state.clarifications ?? []).map(a => [a.question,a.answer]));
  const questions = new Set([...(proposal?.missing_information ?? []), ...previous.keys()]);
  return [...questions].map(question => ({question, answer:previous.get(question) ?? ''}));
}
