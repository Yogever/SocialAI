// Turning values into markup safely.
//
// Every string in this app came from somewhere else — a guest's name from a
// hand-authored file, a line of dialogue from a language model — so none of it
// reaches innerHTML unescaped.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };

export function text(value) {
  return String(value).replace(/[&<>"]/g, (c) => ESCAPES[c]);
}
