// The party log: a running list of things that happened, newest at the top.
//
// It is built only from events, never from snapshots, and that is the point of
// the wire having two channels. A snapshot says who is talking; only an event
// says that they *started*, which is the thing worth a line in a log.

import { text } from "./html.js";

const list = document.getElementById("logList");

const KEEP = 40;

export function note(line) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  const at = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  entry.innerHTML = `<span class="time">${at}</span>${text(line)}`;
  list.prepend(entry);
  while (list.children.length > KEEP) list.lastChild.remove();
}
