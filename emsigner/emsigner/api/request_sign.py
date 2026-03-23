import json
import uuid
from datetime import datetime, timedelta

import frappe
import jwt
from frappe import _
from frappe.utils import get_url, now
from frappe.utils.data import quoted
from markupsafe import escape

from emsigner.emsigner.api.make_sign import _get_jwt_secret, validate_signing_doctype


@frappe.whitelist()
def send_email_request(doctype, docname):
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "write", docname, throw=True)
	doc = frappe.get_doc(doctype, docname)

	for row in doc.signatory_detail:
		if row.signature_status in ("Not Initiated", "Failure"):
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
			frappe.db.set_value(
				"emSigner Signatory Detail",
				row.name,
				{"reference_id": reference_id, "signature_status": "Pending Review"},
			)


def generate_reference_id():
	return uuid.uuid4().hex


def generate_request_link(doctype, docname, recipient_email, reference_id):
	secret = _get_jwt_secret()
	token = jwt.encode(
		{
			"email": recipient_email,
			"ref_id": reference_id,
			"exp": datetime.now() + timedelta(days=7),
		},
		secret,
		algorithm="HS256",
	)

	base_url = get_url("/api/method/emsigner.emsigner.api.make_sign.make_sign")
	return f"{base_url}?doctype={quoted(doctype)}&docname={quoted(docname)}&ref_id={reference_id}&token={token}"


def send_email(signatory_name, recipient_email, request_link, modified_by, doctype, docname, is_reminder=False):
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


@frappe.whitelist()
def resend_reminder(doctype, docname, child_name):
	"""Resend signing email to a specific signatory regardless of current status."""
	frappe.has_permission(doctype, "write", docname, throw=True)
	doc = frappe.get_doc(doctype, docname)

	row = None
	for r in doc.signatory_detail:
		if r.name == child_name:
			row = r
			break

	if not row:
		frappe.throw(_("Signatory not found"))

	if row.signature_status == "Completed":
		frappe.throw(_("{0} has already signed this document.").format(row.signatory_name))

	# Generate a fresh reference and link
	reference_id = generate_reference_id()
	request_link = generate_request_link(
		doctype=doctype,
		docname=docname,
		recipient_email=row.signatory_email,
		reference_id=reference_id,
	)
	send_email(
		row.signatory_name, row.signatory_email, request_link, doc.modified_by, doctype, docname,
		is_reminder=True,
	)

	update_values = {"reference_id": reference_id}
	if row.signature_status == "Not Initiated":
		update_values["signature_status"] = "Pending Review"

	frappe.db.set_value("emSigner Signatory Detail", child_name, update_values)
	return {"message": _("Reminder sent to {0}").format(row.signatory_name)}


@frappe.whitelist()
def add_external_signatory(doctype, docname, signatory_name, signatory_email, sign_position, select_page, page_number=None):
	"""Add an external (non-system-user) signatory to a document."""
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "write", docname, throw=True)

	if not signatory_name or not signatory_email:
		frappe.throw(_("Signatory name and email are required"))

	frappe.utils.validate_email_address(signatory_email, throw=True)

	VALID_SIGN_POSITIONS = (
		"Top-Left", "Top-Center", "Top-Right",
		"Middle-Left", "Middle-Center", "Middle-Right",
		"Bottom-Left", "Bottom-Center", "Bottom-Right",
		"Customize",
	)
	VALID_SELECT_PAGES = ("ALL", "FIRST", "EVEN", "LAST", "ODD", "SPECIFY", "PAGE LEVEL")

	if sign_position not in VALID_SIGN_POSITIONS:
		frappe.throw(_("Invalid sign position"))
	if select_page not in VALID_SELECT_PAGES:
		frappe.throw(_("Invalid select page value"))

	# Get the next idx for the child table
	max_idx = frappe.db.count("emSigner Signatory Detail", {"parent": docname, "parenttype": doctype})

	child = frappe.get_doc({
		"doctype": "emSigner Signatory Detail",
		"parent": docname,
		"parenttype": doctype,
		"parentfield": "signatory_detail",
		"idx": max_idx + 1,
		"signatory_name": signatory_name,
		"signatory_email": signatory_email,
		"sign_position": sign_position,
		"select_page": select_page,
		"page_number": page_number or "",
		"signature_status": "Not Initiated",
	})
	child.db_insert()

	# Update parent's modified so client reload fetches fresh data
	frappe.db.set_value(doctype, docname, "modified", now())

	return {"message": _("Signatory {0} added successfully").format(signatory_name)}


@frappe.whitelist()
def update_coordinates_value(child_doctype, child_name, coordinates, select_page=None, page_number=None, sign_position=None):
	if child_doctype not in ("emSigner Signatory Detail", "emSigner Authorized Signatory"):
		frappe.throw(_("Invalid child doctype"))

	# Verify the child row exists and get parent info
	child = frappe.db.get_value(child_doctype, child_name, ["parent", "parenttype"], as_dict=True)
	if not child:
		frappe.throw(_("Signatory record not found"))

	# Verify user has write permission on the parent document
	frappe.has_permission(child.parenttype, "write", child.parent, throw=True)

	# Validate coordinates
	coords = coordinates.split(",")
	if len(coords) != 4:
		frappe.throw(_("Invalid coordinate format. Expected 4 values: x,y,width,height"))

	for value in coords:
		try:
			float(value.strip())
		except ValueError:
			frappe.throw(_("Coordinates must be numeric values"))

	VALID_SELECT_PAGES = ("ALL", "FIRST", "EVEN", "LAST", "ODD", "SPECIFY", "PAGE LEVEL")
	VALID_SIGN_POSITIONS = (
		"Top-Left", "Top-Center", "Top-Right",
		"Middle-Left", "Middle-Center", "Middle-Right",
		"Bottom-Left", "Bottom-Center", "Bottom-Right",
		"Customize",
	)

	values = {"customize_coordinates": coordinates}

	if sign_position is not None:
		if sign_position not in VALID_SIGN_POSITIONS:
			frappe.throw(_("Invalid sign_position value"))
		values["sign_position"] = sign_position

	if select_page is not None:
		if select_page not in VALID_SELECT_PAGES:
			frappe.throw(_("Invalid select_page value"))
		values["select_page"] = select_page

	if page_number is not None:
		try:
			int(page_number)
		except (ValueError, TypeError):
			if page_number != "":
				frappe.throw(_("Page number must be a valid integer"))
		values["page_number"] = page_number

	frappe.db.set_value(child_doctype, child_name, values)
	return {"message": "Coordinates updated successfully", "coordinates": coordinates}
