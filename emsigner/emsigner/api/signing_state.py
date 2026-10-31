"""Document-scoped signing state. All mutations take the same parent row lock."""

import inspect
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from emsigner.emsigner.utils.py.throw_error import generate_failure_page


def lock_document(doctype, docname):
	meta = frappe.get_meta(doctype)
	field = meta.get_field("signatory_detail")
	if meta.issingle or not field or field.options != "emSigner Signatory Detail":
		generate_failure_page(_("This document is not configured for signing."))
	return frappe.get_doc(doctype, docname, for_update=True)


def active_review(row):
	return bool(
		row.get("signature_status") == "Review In-Progress"
		and row.get("last_tried")
		and get_datetime(row.get("last_tried")) >= now_datetime() - timedelta(minutes=10)
	)


def require_available(rows, target):
	if target.get("signature_status") not in {"Pending Review", "Failure", "Review In-Progress"}:
		generate_failure_page(_("This signing link is no longer available."))
	if any(active_review(row) for row in rows):
		generate_failure_page(_("Another signing session is active. Please try again after it finishes."))


def linked_file_content(doc, *, guest=False):
	"""A token authorizes only the signed attachment on its validated parent."""
	file_doc = frappe.get_doc(
		"File",
		{
			"file_url": doc.get("signed_document"),
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
		},
	)
	if file_doc.attached_to_doctype != doc.doctype or file_doc.attached_to_name != doc.name:
		frappe.throw(_("The signed file is not attached to this document."), frappe.PermissionError)
	if not guest:
		file_doc.check_permission("read")
	# Frappe v16 can decode a PDF as text. Preserve its binary signature bytes.
	if "encodings" in inspect.signature(file_doc.get_content).parameters:
		content = file_doc.get_content(encodings=[])
	else:
		content = file_doc.get_content()
		# v15 only decodes UTF-8, whose re-encoding preserves the source bytes.
		if isinstance(content, str):
			content = content.encode("utf-8")
	if not isinstance(content, bytes):
		frappe.throw(_("The signed PDF could not be read as binary data."))
	return content


def save_signing_document(doc):
	# The signing APIs only edit the app's own fields, including submitted docs.
	# Preserve controller hooks and Version records for child setup/placement edits.
	doc.flags.ignore_validate_update_after_submit = True
	return doc.save(ignore_permissions=True)


def cleanup_expired_sessions():
	"""Remove expired attempt keys in bounded scheduled batches."""
	cutoff = now_datetime() - timedelta(minutes=10)
	rows = frappe.get_all(
		"emSigner Signatory Detail",
		filters={
			"signature_status": "Review In-Progress",
			"last_tried": ["<", cutoff],
		},
		fields=["name", "parenttype", "parent"],
		limit_page_length=100,
		order_by="last_tried asc",
	)
	for old in rows:
		try:
			doc = lock_document(old.parenttype, old.parent)
			row = next((row for row in doc.signatory_detail if row.name == old.name), None)
			if not row or row.signature_status != "Review In-Progress" or active_review(row):
				continue
			frappe.db.set_value("emSigner Signatory Detail", row.name, "signature_status", "Failure")
			frappe.db.delete(
				"__Auth",
				{"doctype": "emSigner Signatory Detail", "name": row.name, "fieldname": "callback_key"},
			)
		except frappe.DoesNotExistError:
			continue


def clear_document_keys(doc, method=None):
	field = doc.meta.get_field("signatory_detail")
	if not field or field.options != "emSigner Signatory Detail":
		return
	names = [row.name for row in doc.get("signatory_detail", []) if row.name]
	if names:
		frappe.db.delete(
			"__Auth",
			{
				"doctype": "emSigner Signatory Detail",
				"name": ["in", names],
				"fieldname": "callback_key",
			},
		)
