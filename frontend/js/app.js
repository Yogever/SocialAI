// The browser, wired together.
//
// This is the only file that knows all the pieces exist, which is what keeps
// them from knowing about each other. Nothing below here reaches sideways: the
// room doesn't know a chat drawer exists, the chat drawer doesn't know about the
// socket's message types, and the debug panel doesn't know about either.
//
// The two channels on the socket land in two different places, and that is the
// whole reason there are two of them: a snapshot replaces what we know about the
// world, while an event is a thing that happened once, in order, and belongs in
// a log, a bubble or a drawer.

import { connect } from "./connection.js";
import { world } from "./world.js";
import { viewer } from "./viewer.js";
import { show } from "./room.js";
import * as controls from "./controls.js";
import * as chat from "./chat.js";
import * as debug from "./debug.js";
import { note } from "./log.js";

controls.arm();
chat.arm();
debug.arm();

show({
  // Clicking a guest means "tell me about them" while the debug panel is open,
  // and "let me talk to them" otherwise. The drawer pauses the party and covers
  // the room, which is the opposite of what you want mid-investigation.
  onPick: (id) => (viewer.debugging ? debug.inspect(id) : chat.open(id)),
});

connect({
  snapshot: (snapshot) => world.describe(snapshot),
  happened: (event) => react(event),
  status: (line) => controls.showStatus(line),
});

function react(event) {
  switch (event.type) {
    case "agent_spoke":
      // A conversation id means it belongs over the room; no id means the
      // guest is talking to whoever opened the drawer.
      if (event.conversation_id) world.noteLine(event.conversation_id, event.text);
      else chat.hear(event);
      break;
    case "agent_drank":
      note(`${event.name} grabbed a drink.`);
      break;
    case "conversation_started":
      note(`${(event.names ?? []).join(" and ")} started talking.`);
      break;
    case "conversation_ended":
      world.forgetLine(event.conversation_id);
      note(`${(event.names ?? []).join(" and ")} wrapped up.`);
      break;
    case "party_ended":
      // The last frame stays on screen: nothing further arrives, so what is
      // drawn is still exactly true, just no longer moving.
      note(`The party ended after ${event.lasted} seconds.`);
      controls.showStatus("party over");
      break;
  }
}
