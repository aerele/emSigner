import { test } from "node:test";
import assert from "node:assert/strict";
import {
  signatureUpdates,
  persistSignatureUpdates,
} from "../public/js/signature_updates.mjs";

test("preset page changes persist without invented coordinates", async () => {
  const rows = [
    {
      child_name: "ROW",
      sign_position: "Top-Left",
      select_page: "FIRST",
      page_number: "",
    },
  ];
  const updates = signatureUpdates(rows, {
    0: { select_page: "SPECIFY", page_number: 3 },
  });
  assert.deepEqual(updates, [
    {
      child_name: "ROW",
      sign_position: "Top-Left",
      select_page: "SPECIFY",
      page_number: "3",
    },
  ]);
  const calls = [];
  assert.equal(
    await persistSignatureUpdates(
      async (...args) => calls.push(args),
      "emSigner Signatory Detail",
      updates
    ),
    1
  );
  assert.equal(calls[0][1].select_page, "SPECIFY");
  assert.equal("coordinates" in calls[0][1], false);
});
test("settings and document edits share validation and preserve a new position", () => {
  const row = { name: "ROW", sign_position: "Top-Left", select_page: "FIRST" };
  const updates = signatureUpdates(
    [row],
    { 0: { sign_position: "Customize", coords: "10,20,60,40" } },
    "name"
  );
  assert.equal(updates[0].sign_position, "Customize");
  assert.equal(updates[0].coordinates, "10,20,60,40");
});
test("invalid custom placement refuses before any API call", () => {
  for (const coords of [
    "",
    "NaN,1,2,3",
    "1,2,0,4",
    "-1,2,3,4",
    "1,2,Infinity,4",
  ])
    assert.throws(() =>
      signatureUpdates([{ child_name: "ROW", sign_position: "Customize" }], {
        0: { coords },
      })
    );
});
test("a failed save keeps edits and stops before later changes", async () => {
  const updates = [
    { child_name: "A" },
    { child_name: "B" },
    { child_name: "C" },
  ];
  const before = structuredClone(updates),
    calls = [];
  await assert.rejects(() =>
    persistSignatureUpdates(
      async (_, args) => {
        calls.push(args.child_name);
        if (args.child_name === "B") throw new Error("refused");
      },
      "emSigner Signatory Detail",
      updates
    )
  );
  assert.deepEqual(calls, ["A", "B"]);
  assert.deepEqual(updates, before);
});
test("old custom positions require a deliberate format review", () => {
  const row = {
    child_name: "ROW",
    sign_position: "Customize",
    select_page: "FIRST",
    customize_coordinates: "10,20,60,40",
    coordinates_reviewed: 0,
  };
  assert.equal(
    signatureUpdates([row], { 0: { coords: row.customize_coordinates } })
      .length,
    1
  );
  row.coordinates_reviewed = 1;
  assert.equal(
    signatureUpdates([row], { 0: { coords: row.customize_coordinates } })
      .length,
    0
  );
});
test("PDF loading preserves bytes, disables evaluation and reports parser refusal", async () => {
  const { loadPdfDocument } = await import("../public/js/pdf_preview.mjs");
  let received;
  const data = "binary\xE2\xE3\xCF\xD3";
  const pdf = { numPages: 2 };
  assert.equal(
    await loadPdfDocument(btoa(data), async () => ({
      getDocument: (args) => {
        received = args;
        return { promise: Promise.resolve(pdf) };
      },
    })),
    pdf
  );
  assert.equal(received.data, data);
  assert.equal(received.isEvalSupported, false);
  await assert.rejects(() =>
    loadPdfDocument(btoa(data), async () => ({
      getDocument: () => ({
        promise: Promise.reject(new Error("invalid PDF")),
      }),
    }))
  );
});
test("preview stays busy through paint and serializes the latest page", async () => {
  const { createPreviewState } = await import("../public/js/pdf_preview.mjs");
  const states = [],
    calls = [];
  let finish;
  const state = createPreviewState((s) => states.push(s));
  assert.equal(states.at(-1).busy, true);
  state.attach({ destroy() {} });
  const draw = state.wrap(async (page) => {
    calls.push(page);
    if (page === 1) await new Promise((r) => (finish = r));
  });
  const first = draw(1);
  await new Promise((r) => setTimeout(r, 0));
  const middle = draw(2),
    last = draw(3);
  assert.equal(states.at(-1).busy, true);
  finish();
  await Promise.all([first, middle, last]);
  assert.deepEqual(calls, [1, 3]);
  assert.equal(states.at(-1).busy, false);
});
test("closing rejects late documents and cannot restore controls", async () => {
  const { createPreviewState } = await import("../public/js/pdf_preview.mjs");
  const states = [];
  let destroyed = 0,
    painted = 0;
  const state = createPreviewState((s) => states.push(s));
  state.dispose();
  assert.equal(
    state.attach({
      destroy() {
        destroyed++;
      },
    }),
    false
  );
  await state.wrap(async () => painted++)();
  assert.equal(destroyed, 1);
  assert.equal(painted, 0);
  assert.equal(states.at(-1).busy, true);
});
test("a paint refusal leaves a visible failed state and cannot send", async () => {
  const { createPreviewState } = await import("../public/js/pdf_preview.mjs");
  const states = [];
  const state = createPreviewState((s) => states.push(s));
  state.attach({ destroy() {} });
  await state.wrap(async () => {
    throw new Error("synthetic paint refusal");
  })();
  assert.deepEqual(states.at(-1), { busy: true, failed: true });
});
