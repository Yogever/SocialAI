// Shared helpers with no dependencies (keeps render.js and ui.js from importing
// each other and forming a cycle).

export function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
