import base64
import hashlib
import hmac
import urllib.parse
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime
from frappe.utils.password import get_decrypted_password
from werkzeug.wrappers import Response

from emsigner.emsigner.api.signing_state import lock_document
from emsigner.emsigner.utils.py.aes_ecb_cipher import AES_ECB_Cipher
from emsigner.emsigner.utils.py.throw_error import SigningFlowError, failure_response, generate_failure_page


@frappe.whitelist(allow_guest=True, methods=["POST"])
def decrypt_method():
	try:
		return decrypt_payload(frappe.request.data.decode("utf-8"))
	except (SigningFlowError, ValueError, frappe.ValidationError):
		frappe.db.rollback()
		return failure_response(_("This signing response is invalid, expired, or already used."))
	except Exception as error:
		frappe.db.rollback()
		frappe.log_error(title="emSigner callback failed", message=type(error).__name__)
		return failure_response(
			_("The signed document could not be saved. Please contact the document owner."), 503
		)


def decrypt_payload(request_payload):
	json_data = parse_request_payload(request_payload)
	reference_no, return_value = json_data.get("Referencenumber"), json_data.get("Returnvalue")
	if not reference_no or not return_value or json_data.get("ReturnStatus", "Success") != "Success":
		generate_failure_page(_("The signing service did not return a signed document."))
	# The same lock protects decryption, state transition and File creation.
	row = locked_signatory(reference_no)
	validate_sign_expiry(row)
	decrypted_data = decrypt_return_value(return_value, row)
	if not is_valid_pdf(decrypted_data):
		generate_failure_page(_("The signing response does not contain a valid PDF."))
	save_signed_pdf(reference_no, decrypted_data)
	return Response(
		status=303,
		headers={
			"Location": "/emsigner_success_page",
			"Cache-Control": "no-store",
			"Referrer-Policy": "no-referrer",
		},
	)


def parse_request_payload(request_payload):
	parsed = urllib.parse.parse_qs(request_payload, max_num_fields=16, strict_parsing=True)
	if any(len(values) != 1 for values in parsed.values()):
		raise ValueError("Repeated callback field")
	return {key: value[0] for key, value in parsed.items()}


def callback_key(row):
	if row.get("signing_reference"):
		value = get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		return base64.b64decode(value, validate=True)
	# One-release compatibility for an already active pre-migration gateway session.
	return get_session_key().encode("utf-8")


def decrypt_return_value(encrypted_value, row):
	cipher = AES_ECB_Cipher(key=callback_key(row))
	# parse_qs already URL-decodes the form. A second unquote can corrupt bytes.
	return cipher.decrypt(encrypted_value, decode=False)


def is_valid_pdf(data):
	return data.startswith(b"%PDF")


def locked_signatory(reference_no):
	initial = get_signatory_details(reference_no)
	if not initial:
		generate_failure_page(_("The signing session is not available."))
	doc = lock_document(initial.parenttype, initial.parent)
	row = next(
		(
			row
			for row in doc.signatory_detail
			if (
				(row.get("signing_reference") == reference_no)
				or (not row.get("signing_reference") and row.get("reference_id") == reference_no)
			)
		),
		None,
	)
	if not row:
		generate_failure_page(_("The signing session is no longer current."))
	return row


def save_signed_pdf(reference_no, content):
	initial = get_signatory_details(reference_no)
	if not initial or initial.get("signature_status") != "Review In-Progress":
		generate_failure_page(_("The signing session is not available."))
	row = locked_signatory(reference_no)
	validate_sign_expiry(row)
	# Compare-and-set is retained as a second guard before any File write.
	table = frappe.qb.DocType("emSigner Signatory Detail")
	condition = (
		table.signing_reference == reference_no
		if row.get("signing_reference")
		else table.reference_id == reference_no
	)
	frappe.qb.update(table).set(table.signature_status, "Completed").where(
		(table.name == row.name) & (table.signature_status == "Review In-Progress") & condition
	).run()
	if frappe.db._cursor.rowcount != 1:
		generate_failure_page(_("The signing response was already used."))
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"content": content,
			"attached_to_doctype": row.parenttype,
			"attached_to_name": row.parent,
			"file_type": "PDF",
			"is_private": 1,
			"attached_to_field": "signed_document",
			"file_name": f"{reference_no}_signed_file.pdf",
			"folder": "Home/Attachments",
		}
	).insert(ignore_permissions=True)
	update_file_url(row.parenttype, row.parent, file_doc.file_url)
	frappe.db.delete(
		"__Auth", {"doctype": "emSigner Signatory Detail", "name": row.name, "fieldname": "callback_key"}
	)
	frappe.flags.commit = True


def get_session_key():
	return get_decrypted_password("emSigner Settings", "emSigner Settings", fieldname="session_key")


def get_signatory_details(reference_no):
	table = frappe.qb.DocType("emSigner Signatory Detail")
	rows = (
		frappe.qb.from_(table)
		.select(
			table.name,
			table.parent,
			table.parenttype,
			table.last_tried,
			table.signature_status,
			table.signing_reference,
		)
		.where(
			(table.signing_reference == reference_no)
			| (
				(table.signing_reference.isnull() | (table.signing_reference == ""))
				& (table.reference_id == reference_no)
			)
		)
		.limit(2)
		.run(as_dict=True)
	)
	return rows[0] if len(rows) == 1 else None


def validate_sign_expiry(signatory):
	if signatory.get("signature_status") != "Review In-Progress" or not signatory.get("last_tried"):
		generate_failure_page(_("No active signing session was found."))
	age = now_datetime() - get_datetime(signatory.get("last_tried"))
	if age < timedelta(0) or age > timedelta(minutes=10):
		generate_failure_page(_("The signing session has expired. Please request a new link."))


def update_signatory_details(name, values):
	frappe.db.set_value("emSigner Signatory Detail", name, values)


def update_file_url(doctype, docname, url):
	frappe.db.set_value(doctype, docname, "signed_document", url)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def signing_failed(reference=None, token=None):
	try:
		row = locked_signatory(reference)
		validate_sign_expiry(row)
		expected = hmac.new(callback_key(row), reference.encode(), hashlib.sha256).hexdigest()
		if not token or not hmac.compare_digest(expected, token):
			generate_failure_page(_("Invalid signing response."))
		update_signatory_details(row.name, {"signature_status": "Failure"})
		frappe.db.delete(
			"__Auth", {"doctype": "emSigner Signatory Detail", "name": row.name, "fieldname": "callback_key"}
		)
		frappe.flags.commit = True
		return failure_response(_("Signing did not finish. You can use your email link to try again."), 200)
	except (SigningFlowError, frappe.ValidationError, ValueError, TypeError):
		frappe.db.rollback()
		return failure_response(_("This signing response is invalid, expired, or already used."))
