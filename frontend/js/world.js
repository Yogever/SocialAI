// The party as the backend last described it.
//
// Nothing in the browser decides anything about the world. A snapshot arrives
// and replaces what we knew — latest-wins, so a dropped frame costs nothing and
// a browser that reconnects is completely correct again from the next message.
//
// The one thing a guest keeps that the backend didn't send is where they are
// being *drawn*. Snapshots arrive thirty times a second and frames are painted
// sixty, so each guest eases toward the position the backend reports rather than
// snapping to it. That drift is presentation, never truth: it is read by the
// renderer and by nothing else.

export class Guest {
  constructor(reported) {
    this.drawnAt = [reported.pos[0], reported.pos[1]];
    this.describe(reported);
  }

  describe(reported) {
    this.id = reported.id;
    this.name = reported.name;
    this.age = reported.age;
    this.at = reported.pos;
    this.stats = reported.stats;
    this.doing = reported.action;
    this.conversationId = reported.conversation_id;
  }

  get isWalking() {
    return this.doing === "walking";
  }

  get hasADrink() {
    return this.doing === "drinking";
  }

  driftTowardsTruth(rate) {
    this.drawnAt[0] += (this.at[0] - this.drawnAt[0]) * rate;
    this.drawnAt[1] += (this.at[1] - this.drawnAt[1]) * rate;
  }
}

class World {
  constructor() {
    this.guests = new Map();
    // The latest thing said in each conversation, for the bubble above it. Only
    // ever the latest: a bubble is a moment, not a transcript.
    this.latestLine = new Map();
  }

  describe(snapshot) {
    const present = new Set();
    for (const reported of snapshot.agents) {
      present.add(reported.id);
      const known = this.guests.get(reported.id);
      if (known) known.describe(reported);
      else this.guests.set(reported.id, new Guest(reported));
    }
    for (const id of [...this.guests.keys()]) {
      if (!present.has(id)) this.guests.delete(id);
    }
  }

  guest(id) {
    return this.guests.get(id) ?? null;
  }

  everyone() {
    return [...this.guests.values()];
  }

  conversations() {
    // Who is talking to whom is derivable from who claims which conversation, so
    // it is derived rather than tracked — there is no second copy to fall out of
    // step with the snapshots.
    const groups = new Map();
    for (const guest of this.guests.values()) {
      if (!guest.conversationId) continue;
      if (!groups.has(guest.conversationId)) groups.set(guest.conversationId, []);
      groups.get(guest.conversationId).push(guest);
    }
    return [...groups.entries()]
      .filter(([, members]) => members.length >= 2)
      .map(([id, members]) => ({ id, members, line: this.latestLine.get(id) }));
  }

  noteLine(conversationId, line) {
    this.latestLine.set(conversationId, line);
  }

  forgetLine(conversationId) {
    this.latestLine.delete(conversationId);
  }
}

export const world = new World();
