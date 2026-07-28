// Entry point: wire net -> state/ui, start the render loop, arm the controls.

import { connect } from "./net.js";
import { applySnapshot } from "./state.js";
import { start as startRender } from "./render.js";
import { onEvent, onStatus, initControls } from "./ui.js";

initControls();

connect({
  onState: (snapshot) => applySnapshot(snapshot), // state channel: latest-wins
  onEvent: (msg) => onEvent(msg),                 // event channel: append/ordered
  onStatus: (text) => onStatus(text),
});

startRender();
