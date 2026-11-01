import json
import uuid
from datetime import datetime, timedelta, timezone

import frappe
import jwt
from frappe import _
from frappe.utils import get_datetime, get_url, now, now_datetime
from frappe.utils.data import quoted
from markupsafe import escape

from emsigner.emsigner.api.emsigner import validate_settings
from emsigner.emsigner.api.make_sign import (
	_get_jwt_secret,
	_parse_coordinates,
	validate_placement,
	validate_signing_doctype,
)
from emsigner.emsigner.api.signing_state import active_review, lock_document, save_signing_document


@frappe.whitelist(methods=["POST"])
def send_email_request(doctype, docname):
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "write", docname, throw=True)
	validate_settings(frappe.get_doc("emSigner Settings"))
	doc = lock_document(doctype, docname)

	for row in doc.signatory_detail:
		if row.signature_status in ("Not Initiated", "Failure"):
			validate_placement(row)
			reference_id = generate_reference_id()
			request_link = generate_request_link(
				doctype=doctype,
				docname=docname,
				recipient_email=row.signatory_email,
				reference_id=reference_id,
			)
			send_email(
				row.signatory_name, row.signatory_email, request_link, doc.modified_by, doctype, docname
			)
			row.reference_id, row.signature_status = reference_id, "Pending Review"
			row.last_reminded = now()
	save_signing_document(doc)


def generate_reference_id():
	return uuid.uuid4().hex


def generate_request_link(doctype, docname, recipient_email, reference_id):
	validate_settings(frappe.get_doc("emSigner Settings"))
	secret = _get_jwt_secret()
	token = jwt.encode(
		{
			"email": recipient_email,
			"ref_id": reference_id,
			"exp": datetime.now(timezone.utc) + timedelta(days=7),
			"purpose": "emsigner-sign",
			"doctype": doctype,
			"docname": docname,
		},
		secret,
		algorithm="HS256",
	)

	base_url = get_url("/api/method/emsigner.emsigner.api.make_sign.make_sign")
	return (
		f"{base_url}?doctype={quoted(doctype)}&docname={quoted(docname)}&ref_id={reference_id}&token={token}"
	)


def send_email(
	signatory_name, recipient_email, request_link, modified_by, doctype, docname, is_reminder=False
):
	subject = _("Reminder: Request for Signature") if is_reminder else _("Request for Signature")
	frappe.sendmail(
		recipients=[recipient_email],
		subject=subject,
		message=get_email_content(signatory_name, request_link, modified_by),
		reference_doctype=doctype,
		reference_name=docname,
	)


def get_email_content(signatory_name, link, author):
	safe_name = escape(signatory_name)
	safe_author = escape(frappe.utils.get_fullname(author))
	safe_link = escape(link)

	return f"""
	<html>
	<body>
		<p>Dear {safe_name},</p>

		<p>I hope you're doing well.</p>

		<p>Please review and sign the document using the link below:</p>

		<p><a href="{safe_link}" style="color: #007bff; text-decoration: none; font-weight: bold;">Sign Document</a></p>

		<p>If you have any questions, feel free to reach out.</p>

		<p>Best regards,</p>
		<p>{safe_author}</p>
	</body>
	</html>
	"""


@frappe.whitelist(methods=["POST"])
def resend_reminder(doctype, docname, child_name):
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "write", docname, throw=True)
	validate_settings(frappe.get_doc("emSigner Settings"))
	doc = lock_document(doctype, docname)
	row = next((row for row in doc.signatory_detail if row.name == child_name), None)
	if not row or row.signature_status in {"Completed", "Rejected"}:
		frappe.throw(_("This signatory cannot receive a new link."))
	if active_review(row):
		frappe.throw(_("This signing session is still active. Wait until it finishes."))
	if row.get("last_reminded") and now_datetime() - get_datetime(row.last_reminded) < timedelta(minutes=1):
		frappe.throw(_("Wait one minute before sending another reminder."))
	validate_placement(row)
	row.reference_id, row.signature_status = generate_reference_id(), "Pending Review"
	row.last_reminded = now()
	link = generate_request_link(doctype, docname, row.signatory_email, row.reference_id)
	send_email(
		row.signatory_name, row.signatory_email, link, doc.modified_by, doctype, docname, is_reminder=True
	)
	save_signing_document(doc)
	return {"message": _("Reminder sent.")}


@frappe.whitelist(methods=["POST"])
def add_external_signatory(
	doctype, docname, signatory_name, signatory_email, sign_position, select_page, page_number=None
):
	"""Add an external (non-system-user) signatory to a document."""
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "write", docname, throw=True)

	if not signatory_name or not signatory_email:
		frappe.throw(_("Signatory name and email are required"))

	frappe.utils.validate_email_address(signatory_email, throw=True)

	VALID_SIGN_POSITIONS = (
		"Top-Left",
		"Top-Center",
		"Top-Right",
		"Middle-Left",
		"Middle-Center",
		"Middle-Right",
		"Bottom-Left",
		"Bottom-Center",
		"Bottom-Right",
		"Customize",
	)
	VALID_SELECT_PAGES = ("ALL", "FIRST", "EVEN", "LAST", "ODD", "SPECIFY", "PAGE LEVEL")

	if sign_position not in VALID_SIGN_POSITIONS:
		frappe.throw(_("Invalid sign position"))
	if select_page not in VALID_SELECT_PAGES:
		frappe.throw(_("Invalid select page value"))

	doc = lock_document(doctype, docname)
	if any(active_review(row) for row in doc.signatory_detail):
		frappe.throw(_("Wait until the active signing session finishes before adding a signatory."))
	doc.append(
		"signatory_detail",
		{
			"signatory_name": signatory_name,
			"signatory_email": signatory_email,
			"sign_position": sign_position,
			"select_page": select_page,
			"page_number": page_number or "",
			"signature_status": "Not Initiated",
		},
	)
	save_signing_document(doc)
	return {"message": _("Signatory added.")}


@frappe.whitelist(methods=["POST"])
def update_coordinates_value(
	child_doctype, child_name, coordinates=None, select_page=None, page_number=None, sign_position=None
):
	if child_doctype not in ("emSigner Signatory Detail", "emSigner Authorized Signatory"):
		frappe.throw(_("Invalid child doctype"))

	# Verify the child row exists and get parent info
	child = frappe.db.get_value(child_doctype, child_name, ["parent", "parenttype"], as_dict=True)
	if not child:
		frappe.throw(_("Signatory record not found"))

	# Verify user has write permission on the parent document
	frappe.has_permission(child.parenttype, "write", child.parent, throw=True)

	parent = (
		lock_document(child.parenttype, child.parent)
		if child_doctype == "emSigner Signatory Detail"
		else frappe.get_doc(child.parenttype, child.parent, for_update=True)
	)
	row = next(
		(
			row
			for row in parent.get(
				"signatory_detail"
				if child_doctype == "emSigner Signatory Detail"
				else "authorized_signatory",
				[],
			)
			if row.name == child_name
		),
		None,
	)
	if not row:
		frappe.throw(_("Signatory record not found."))
	if child_doctype == "emSigner Signatory Detail" and row.signature_status not in {
		"Not Initiated",
		"Failure",
		"Pending Review",
	}:
		frappe.throw(_("Placement cannot change after a signing link was sent."))
	position = sign_position if sign_position is not None else row.sign_position
	if position == "Customize" and not _parse_coordinates(coordinates or row.customize_coordinates):
		frappe.throw(
			_("Set four finite coordinates: left, top, width, height. Width and height must be positive.")
		)
	if coordinates and not _parse_coordinates(coordinates):
		frappe.throw(_("The signature coordinates are invalid."))

	VALID_SELECT_PAGES = ("ALL", "FIRST", "EVEN", "LAST", "ODD", "SPECIFY", "PAGE LEVEL")
	VALID_SIGN_POSITIONS = (
		"Top-Left",
		"Top-Center",
		"Top-Right",
		"Middle-Left",
		"Middle-Center",
		"Middle-Right",
		"Bottom-Left",
		"Bottom-Center",
		"Bottom-Right",
		"Customize",
	)

	values = {} if coordinates is None else {"customize_coordinates": coordinates}

	if sign_position is not None:
		if sign_position not in VALID_SIGN_POSITIONS:
			frappe.throw(_("Invalid sign_position value"))
		values["sign_position"] = sign_position

	if select_page is not None:
		if select_page not in VALID_SELECT_PAGES:
			frappe.throw(_("Invalid select_page value"))
		values["select_page"] = select_page

	page = select_page if select_page is not None else row.select_page
	if page == "SPECIFY":
		try:
			if int(page_number if page_number is not None else row.page_number) < 1:
				raise ValueError()
		except (ValueError, TypeError):
			frappe.throw(_("Select a positive page number."))
	if page_number is not None:
		try:
			int(page_number)
		except (ValueError, TypeError):
			if page_number != "":
				frappe.throw(_("Page number must be a valid integer"))
		values["page_number"] = page_number

	if coordinates:
		values["coordinates_reviewed"] = 1
	if child_doctype == "emSigner Signatory Detail" and row.signature_status == "Pending Review":
		# Changed placement invalidates an unused emailed link. It cannot silently
		# alter what an older invitation will sign.
		values.update(signature_status="Not Initiated", reference_id="", signing_reference="")
	row.update(values)
	save_signing_document(parent)
	return {"message": "Coordinates updated successfully", "coordinates": coordinates}


@frappe.whitelist(methods=["POST"])
def prepare_placement_review(doctype, docname, child_name):
	"""Revoke an unused invitation so its owner can review stored placement."""
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "write", docname, throw=True)
	doc = lock_document(doctype, docname)
	row = next((row for row in doc.signatory_detail if row.name == child_name), None)
	if not row or row.signature_status in {"Completed", "Rejected"} or active_review(row):
		frappe.throw(_("This signatory cannot change placement while signing is active or complete."))
	row.update(
		{"signature_status": "Not Initiated", "reference_id": "", "signing_reference": "", "callback_key": ""}
	)
	save_signing_document(doc)
	return {"message": _("The old link is revoked. Review the position and send a new link.")}
