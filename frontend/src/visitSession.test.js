import test from "node:test";
import assert from "node:assert/strict";
import { createVisitSession } from "./visitSession.js";

test("same page deduplicates bootstrap and shares its token", async () => {
  let calls = 0;
  const visit = createVisitSession(async () => { calls++; return { token: "visit-a" }; });
  assert.equal(visit.token, null);
  const a = visit.start();
  const b = visit.start();
  assert.equal(a, b);
  await Promise.all([a, b]);
  assert.equal(calls, 1);
  assert.equal(visit.token, "visit-a");
});

test("new page has no token or history from the previous page", async () => {
  let calls = 0;
  const createGuest = async () => ({ token: "visit-" + ++calls, booking: { state: "DISCOVERY" } });
  const first = createVisitSession(createGuest);
  await first.start();
  const next = createVisitSession(createGuest);
  assert.equal(next.token, null);
  assert.equal((await next.start()).booking.state, "DISCOVERY");
  assert.notEqual(first.token, next.token);
});

test("failed bootstrap can be retried without a stale credential", async () => {
  let calls = 0;
  const visit = createVisitSession(async () => {
    if (++calls === 1) throw new Error("network");
    return { token: "recovered" };
  });
  await assert.rejects(visit.start(), /network/);
  assert.equal(visit.token, null);
  await visit.start();
  assert.equal(visit.token, "recovered");
});
