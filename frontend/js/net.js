// WebSocket client. Delivers messages to handlers; sends control intent.
//
// The client sends *intent* (pause, open_chat, user_message) — never world
// state. It has no authority; it asks, the backend decides.

let ws = null;
let handlers = {};

export function connect(h) {
  handlers = h;
  open();
}

function open() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => handlers.onStatus?.("live");
  ws.onclose = () => {
    handlers.onStatus?.("reconnecting…");
    // full snapshots make reconnection free — just re-open and the next
    // message rebuilds the whole world.
    setTimeout(open, 1000);
  };
  ws.onerror = () => ws.close();

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "world_state") {
      handlers.onState?.(msg);
    } else {
      handlers.onEvent?.(msg);
    }
  };
}

export function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}
