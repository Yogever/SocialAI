// The socket.
//
// Two kinds of message come down it and they are handled differently on
// purpose: a snapshot is the whole world, latest-wins; everything else is
// something that *happened*, in order, once.
//
// Everything that goes up it is intent — pause the party, open a chat, say
// this. The browser has no authority. It asks, and the backend decides.

let socket = null;
let listener = {};

export function connect(handlers) {
  listener = handlers;
  open();
}

function open() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${scheme}://${location.host}/ws`);

  socket.onopen = () => listener.status?.("live");
  socket.onerror = () => socket.close();
  socket.onclose = () => {
    listener.status?.("reconnecting…");
    // Reconnecting costs nothing: the next snapshot is the entire world again,
    // so there is nothing to catch up on and nothing to replay.
    setTimeout(open, 1000);
  };

  socket.onmessage = (message) => {
    const payload = JSON.parse(message.data);
    if (payload.type === "world_state") listener.snapshot?.(payload);
    else listener.happened?.(payload);
  };
}

export function ask(request) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(request));
}
