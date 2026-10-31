/** Build the API edits for both preset and custom signature positions. */
export function signatureUpdates(rows, edits, nameField = "child_name") {
  const result = [];
  for (const [index, edit] of Object.entries(edits)) {
    const row = rows[Number(index)];
    if (!row || !row[nameField]) continue;
    const position = edit.sign_position ?? row.sign_position;
    const coordinates = edit.coords ?? row.customize_coordinates ?? "";
    if (position === "Customize") {
      const parts = coordinates.split(",").map(Number);
      if (
        parts.length !== 4 ||
        parts.some((part) => !Number.isFinite(part)) ||
        parts[0] < 0 ||
        parts[1] < 0 ||
        parts[2] <= 0 ||
        parts[3] <= 0
      ) {
        throw new Error("Set a custom position before saving.");
      }
    }
    const page = edit.select_page ?? row.select_page;
    const pageNumber = String(edit.page_number ?? row.page_number ?? "");
    if (
      (position !== "Customize" || row.coordinates_reviewed) &&
      position === row.sign_position &&
      coordinates === (row.customize_coordinates ?? "") &&
      page === row.select_page &&
      pageNumber === String(row.page_number ?? "")
    )
      continue;
    result.push({
      child_name: row[nameField],
      sign_position: position,
      select_page: page,
      page_number: pageNumber,
      ...(coordinates ? { coordinates } : {}),
    });
  }
  return result;
}

export async function persistSignatureUpdates(call, childDoctype, updates) {
  // Stop on the first refusal. The caller keeps the edits for an explicit retry.
  for (const update of updates) {
    await call("emsigner.emsigner.api.request_sign.update_coordinates_value", {
      child_doctype: childDoctype,
      ...update,
    });
  }
  return updates.length;
}
