// What the person watching is looking at.
//
// Deliberately separate from world.js. Everything in there is the backend's
// truth and arrives over the socket; everything in here is this browser's own —
// which guest the mouse is over, which drawer is open, whether the lights are
// on. None of it is ever sent anywhere as authority: the browser asks the
// backend to pause the party, and then believes the backend.

export const viewer = {
  hovering: null,       // guest id under the cursor
  chattingWith: null,   // guest id whose drawer is open
  inspecting: null,     // guest id pinned in the debug panel
  night: true,
  paused: false,
  speed: 1,
  debugging: false,
};
