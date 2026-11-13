export function createRequestFence() {
  let generation = 0;
  return {
    issue(identity) { generation += 1; return { generation, identity }; },
    invalidate() { generation += 1; },
    isCurrent(token, identity) { return token?.generation === generation && token.identity === identity; },
  };
}
