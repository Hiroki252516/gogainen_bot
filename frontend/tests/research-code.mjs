export function newResearchCode() {
  return `${Date.now()}${String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0")}`;
}
