# External signing upgrade

This release changes signing links, callbacks, saved placement data and API methods.
Test the upgrade on a copy of the site before release. Keep a database, private file and site configuration backup. Include the site
`encryption_key`. Do not run signing tests on a business site.

## Deploy

1. Install the declared app dependencies. This includes PyJWT and pypdf.
2. Run `bench --site SITE migrate`. The patch preserves an explicit gateway. If
   the old Single has no stored gateway, it keeps the prior demo gateway.
3. Run `bench build --app emsigner`, restart the bench services, and confirm that
   the scheduler runs the five-minute expired-session cleanup.
4. Check a normal user and a Guest with the demo account before enabling a live
   signing account. Check certificate trust, callback delivery, signature mode and
   the actual rectangle on the signed PDF. These provider checks need a live demo.

Only the HTTPS production, demo and test emSigner hosts at
`/eMsecure/V3_0/Index` are accepted. A blank gateway uses the demo host. A live
production gateway must be an explicit setting.

## Links and signing state

New email links use a dedicated random signing secret and UTC expiry. Each link
binds the email, document type, document name and reference. The AES transport key
is separate. Each signing attempt has its own random encryption key and provider
reference. The provider reference is at most 20 characters.

The migration permits old reference-key and session-key email tokens for seven
days. It stores a fixed `legacy_links_until` cutoff. Repeated migrations and
settings saves do not extend that cutoff or replace the signing secret. Remove
the compatibility path in the next release after that period. Rotating the new
signing secret revokes new outstanding email links; send replacements afterward.

Only one signing attempt can be active on a document. Completed signatures cannot
start again. Each callback is single use. A late response from an older attempt
cannot replace a newer attempt or PDF. The next signer receives the saved signed
PDF as binary data. A missing signed attachment fails visibly; it does not print
an unsigned replacement.

An attempt expires after ten minutes. Its key is removed after completion or an
authenticated failure. Normal document deletion also removes its child callback
keys in the same transaction. The scheduler removes expired keys in batches of at most
100 every five minutes. Scheduler downtime or a backlog can delay physical key
cleanup; expired attempts still cannot complete. Reissuing a reminder does not
change an active attempt, and reminders have a one-minute minimum interval.

Guest access comes from the validated link. It covers only the named document and
its attached signed PDF. Guest flow does not set global `ignore_permissions`.
Logged-in users must also have read permission. New signed PDFs are private. This patch does not change the visibility of older
File records. The
normal download API checks File read access and uses the server's attachment;
client JSON cannot select another private file.

## Placement and document history

The provider documents `CustomizeCoordinates` as left, top, width, height. The old
picker stored different third and fourth values. No safe conversion covers all
old records, including values from the external picker. Existing custom positions
therefore need review and a fresh save before signing. Reposition them in the
preview, check the result, and send a new link. For an existing unused link, open
Signing Status and use Review placement. This action revokes that link and opens
the preview without marking the old coordinates as reviewed. Old values are retained; the patch
does not guess or overwrite them. Preset page changes can be saved without custom
coordinates. Coordinates must be finite and have positive width and height.

Changing an unused pending placement revokes its old email link. Active and
completed placements cannot change. Fetch Signatory Info refuses after signing
starts; it cannot delete completed or in-flight rows. Adding signatories uses
parent save hooks and versions. Settings setup also enables the DocType. Reset
removes its signing configuration while retaining stored signing fields, PDFs and
history. It no longer deletes the custom fields as a side effect of disabling a
document type.

The gateway form is returned as HTML from the email-link API. It supports Guest
users and a keyboard-accessible Continue button if automatic posting is blocked.
It does not redirect a Guest through Desk. Browser failures return an escaped HTML
message. AJAX validation uses typed errors. Guest outcome pages do not expose the
parent document name or a Desk link.

## API and asset changes

`send_email_request`, `resend_reminder`, `add_external_signatory`,
`update_coordinates_value`, `prepare_placement_review`, and
`fetch_emsigner_authorized_signatory` now require
POST. `update_coordinates_value` identifies the exact child row by
`child_doctype` and `child_name`. `coordinates` is optional for preset page edits.
The former `place_signature_page` and `upload_file` endpoints were removed by this
PR. Update callers before release; do not restore their former file-selection
behaviour. The old Desk redirect is no longer used by new links.

The PDF library and its worker use pinned integrity hashes. A failed library,
worker or PDF read keeps a visible preview error and disables the save/send
button. Controls stay disabled until the PDF is loaded and painted. Page renders
are serialized, and closing a dialog releases its PDF worker. Close and reopen
the dialog to retry. The shared loader disables dynamic
PDF code evaluation. Viewer layout code is still duplicated; this release does
not rewrite the placement components.

## Rollback

Stop new signing requests before rollback and let active attempts finish or expire.
Keep the new fields and encrypted state until that process is complete. Old code
cannot process new attempt references or new email tokens. Restore the matching
database, private files and code together if a full rollback is required. Re-send
links only after the target version and its settings are in place.

## Tests

Use an isolated bench and a site whose name starts with `test_`. From the bench:

```sh
EMSIGNER_TEST_ISOLATION='REPEATABLE READ' env/bin/python apps/emsigner/scripts/run_tests.py test_emsigner
```

From the app directory:

```sh
node --test emsigner/tests/test_signature_updates.mjs
```

The native tests commit synthetic state to check GET persistence and real races.
They remove their document/file fixtures and restore settings. The custom test
DocType remains on the disposable test site. CI runs native tests and builds on
Frappe v15 and v16.53.0. A green unit or database run does not prove gateway
acceptance, cryptographic signature validity, or the complete Desk browser flow.

Provider format source: [emSigner signing documents](https://developers.emsigner.com/signer-gateway/api-reference/signing-documents.html).
