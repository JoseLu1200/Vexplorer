export const DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.97;

/**
 * Evaluate similarity matches and detect whether the top match meets the near-duplicate threshold.
 *
 * @param {Array<object>|null|undefined} matches
 * @param {{ threshold?: number }} [options]
 * @returns {{ found: boolean, match: object|null, score?: number, runId?: string, resultRevision?: number|null, label?: string, url?: string }}
 */
export function evaluateDuplicatePrecedent(
  matches,
  { threshold = DEFAULT_NEAR_DUPLICATE_THRESHOLD } = {},
) {
  if (!Array.isArray(matches) || matches.length === 0) {
    return { found: false, match: null };
  }

  const effectiveThreshold = Number.isFinite(threshold)
    ? threshold
    : DEFAULT_NEAR_DUPLICATE_THRESHOLD;

  let topMatch = null;
  for (const candidate of matches) {
    if (
      !candidate ||
      typeof candidate.run_id !== "string" ||
      !candidate.run_id.trim() ||
      !Number.isFinite(candidate.score)
    ) {
      continue;
    }
    if (!topMatch || candidate.score > topMatch.score) {
      topMatch = candidate;
    }
  }

  if (!topMatch || topMatch.score < effectiveThreshold) {
    return { found: false, match: null };
  }

  const label = topMatch.label ?? topMatch.name ?? topMatch.run_id;
  const resultRevision = Number.isInteger(topMatch.result_revision)
    ? topMatch.result_revision
    : null;

  return {
    found: true,
    match: topMatch,
    score: topMatch.score,
    runId: topMatch.run_id,
    resultRevision,
    label,
    url: `?run=${encodeURIComponent(topMatch.run_id)}`,
  };
}

/**
 * Format Spanish banner copy and link metadata for a near-duplicate precedent evaluation.
 *
 * @param {{ found?: boolean, match?: object|null, score?: number, runId?: string, resultRevision?: number|null, label?: string, url?: string }|null|undefined} evaluation
 * @returns {{ visible: boolean, title: string, message: string, linkText: string, linkUrl: string, label: string, scoreText: string }}
 */
export function formatDuplicatePrecedentBanner(evaluation) {
  if (!evaluation?.found || !evaluation.match) {
    return {
      visible: false,
      title: "",
      message: "",
      linkText: "",
      linkUrl: "",
      label: "",
      scoreText: "",
    };
  }

  const scoreText = Number.isFinite(evaluation.score)
    ? evaluation.score.toFixed(2)
    : "—";
  const label = String(evaluation.label ?? evaluation.runId ?? "Precedente");
  const title = "¿Ya hemos fabricado algo así?";
  const message = `${title} Coincidencia muy alta (similitud ${scoreText})`;
  const linkText = Number.isInteger(evaluation.resultRevision)
    ? `Abrir ${label} (rev. ${evaluation.resultRevision})`
    : `Abrir ${label}`;

  return {
    visible: true,
    title,
    message,
    linkText,
    linkUrl: evaluation.url ?? `?run=${encodeURIComponent(evaluation.match.run_id)}`,
    label,
    scoreText,
  };
}
