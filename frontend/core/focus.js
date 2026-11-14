export function nextFocusTarget(focusables, active, backwards = false) {
  if (!focusables?.length) return null;
  const current = focusables.indexOf(active);
  if (current < 0) return backwards ? focusables.at(-1) : focusables[0];
  return focusables[(current + (backwards ? -1 : 1) + focusables.length) % focusables.length];
}
