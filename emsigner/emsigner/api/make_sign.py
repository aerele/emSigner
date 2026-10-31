import base64
import io
import json
import math
import secrets
from datetime import datetime, timedelta, timezone

import frappe
import jwt
from frappe import _
from frappe.utils import get_datetime, now, now_datetime
from frappe.utils.pdf import get_pdf

from emsigner.emsigner.api.emsigner import get_emsigner_parameters
from emsigner.emsigner.api.signing_state import (
	active_review,
	linked_file_content,
	lock_document,
	require_available,
	save_signing_document,
)
from emsigner.emsigner.utils.py.throw_error import SigningFlowError, failure_response, generate_failure_page


def _get_jwt_secret():
	return frappe.get_doc("emSigner Settings").get_password("signing_secret")


def _decode_signing_token(token, doctype, docname, ref_id):
	settings = frappe.get_doc("emSigner Settings")
	try:
		payload = jwt.decode(
			token,
			_get_jwt_secret(),
			algorithms=["HS256"],
			options={"require": ["exp", "email", "ref_id", "doctype", "docname", "purpose"]},
		)
		if (
			payload.get("purpose"),
			payload.get("doctype"),
			payload.get("docname"),
			payload.get("ref_id"),
		) != ("emsigner-sign", doctype, docname, ref_id):
			raise jwt.InvalidTokenError()
		return payload
	except jwt.InvalidTokenError:
		# One-release overlap for existing emailed links. The migration fixes a
		# seven-day cutoff; it must not be extended by settings saves or retries.
		until = settings.get("legacy_links_until")
		if not until or now_datetime() > get_datetime(until):
			raise
		for key in (settings.get_password("session_key", raise_exception=False), ref_id):
			if not key:
				continue
			try:
				payload = jwt.decode(token, key, algorithms=["HS256"], options={"require": ["exp", "email"]})
				if payload.get("purpose") or (payload.get("ref_id") and payload["ref_id"] != ref_id):
					continue
				return payload
			except jwt.InvalidTokenError:
				continue
		raise jwt.InvalidTokenError()


def validate_signing_doctype(doctype):
	"""Validate that the doctype is enabled for signing in emSigner Settings."""
	enabled = frappe.get_all(
		"emSigner Doctype", filters={"parent": "emSigner Settings"}, pluck="doctype_name"
	)
	if doctype not in enabled:
		generate_failure_page("This document type is not enabled for signing.")


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def make_sign():
	try:
		doctype, docname, ref_id, token = (
			frappe.form_dict.get(key) for key in ("doctype", "docname", "ref_id", "token")
		)
		if not all(isinstance(value, str) and value for value in (doctype, docname, ref_id, token)):
			generate_failure_page(_("Missing required parameters."))
		validate_signing_doctype(doctype)
		# Token verification precedes the locking parent/signatory reads.
		details = verify_signatory(doctype, docname, ref_id, token)
		if frappe.session.user != "Guest":
			frappe.has_permission(doctype, "read", docname, throw=True)
		response = initiate_signing_process(doctype, docname, ref_id, **details)
		# Email links are GETs. Frappe otherwise rolls the state back.
		frappe.flags.commit = True
		return response
	except SigningFlowError as error:
		frappe.db.rollback()
		return failure_response(str(error))
	except frappe.ValidationError:
		frappe.db.rollback()
		return failure_response(
			_("The owner must check the signing settings and document before you try again.")
		)
	except frappe.PermissionError:
		frappe.db.rollback()
		return failure_response(_("You do not have permission to open this document."), 403)
	except Exception as error:
		frappe.db.rollback()
		frappe.log_error(title="emSigner preparation failed", message=type(error).__name__)
		return failure_response(
			_("The signing request could not be prepared. Please ask the document owner for help."), 503
		)


def initiate_signing_process(doctype, docname, ref_id, **signatory_details):
	validate_placement(signatory_details)
	content = get_document_content(doctype, docname, signatory_details)
	attempt_ref = secrets.token_hex(10)  # Provider ReferenceNumber limit: 20 characters.
	key = secrets.token_bytes(32)
	response = send_for_signing(attempt_ref, content, {**signatory_details, "session_key": key})
	update_signatory_status(doctype, docname, ref_id, attempt_ref, key)
	return response


def validate_placement(row):
	if row.get("sign_position") == "Customize" and (
		not row.get("coordinates_reviewed") or not _parse_coordinates(row.get("customize_coordinates"))
	):
		generate_failure_page(
			_("The owner must review and save the custom signature position, then send a new link.")
		)


def get_document_content(doctype, docname, signatory_details):
	doc = frappe.get_doc(doctype, docname, for_update=True)
	if doc.get("signed_document"):
		return linked_file_content(doc, guest=frappe.session.user == "Guest")
	old_print = frappe.flags.get("ignore_print_permissions")
	try:
		# Only this already token-validated parent's print is authorized.
		frappe.flags.ignore_print_permissions = frappe.session.user == "Guest"
		html = frappe.get_print(
			doctype=doctype,
			name=docname,
			print_format=doc.get("requested_print_format"),
			letterhead=doc.get("requested_letter_head"),
		)
		return get_pdf(html)
	finally:
		frappe.flags.ignore_print_permissions = old_print


def send_for_signing(ref_id, content, signatory_details):
	return get_emsigner_parameters(
		reference_id=ref_id,
		session_key=signatory_details["session_key"],
		signatory_name=signatory_details.get("signatory_name", ""),
		file_content=base64.b64encode(content).decode("utf-8"),
		select_page=signatory_details.get("select_page") or "",
		page_number=signatory_details.get("page_number") or "",
		page_level_coordinates=signatory_details.get("page_level_coordinates") or "",
		signature_position=signatory_details.get("sign_position") or "",
		customize_coordinates=signatory_details.get("customize_coordinates", "")
		if signatory_details.get("sign_position") == "Customize"
		else "",
		reason="",
	)


def update_signatory_status(doctype, docname, ref_id, attempt_ref, key):
	from frappe.utils.password import set_encrypted_password

	doc = lock_document(doctype, docname)
	row = next((row for row in doc.signatory_detail if row.reference_id == ref_id), None)
	if not row:
		generate_failure_page(_("The signing link is no longer available."))
	require_available(doc.signatory_detail, row)
	set_encrypted_password(
		"emSigner Signatory Detail", row.name, base64.b64encode(key).decode(), fieldname="callback_key"
	)
	frappe.db.set_value(
		"emSigner Signatory Detail",
		row.name,
		{
			"signature_status": "Review In-Progress",
			"last_tried": now(),
			"signing_reference": attempt_ref,
			"callback_key": "********",
		},
	)


def verify_signatory(doctype, docname, ref_id, token):
	try:
		payload = _decode_signing_token(token, doctype, docname, ref_id)
	except jwt.ExpiredSignatureError:
		generate_failure_page(_("The signing link has expired. Please request a new one."))
	except jwt.InvalidTokenError:
		generate_failure_page(_("Invalid signing link."))
	return verify_and_get_signatory(doctype, docname, payload["email"], ref_id)


def verify_and_get_signatory(doctype, docname, email, ref_id):
	parent_doc_fields = get_parent_document_fields(doctype, docname)
	signatory_details = get_signatory_details(doctype, docname)

	authorized_signatory = None

	for row in signatory_details:
		if row["signatory_email"] == email and row["reference_id"] == ref_id:
			require_available(signatory_details, row)
			authorized_signatory = row
			break

	if not authorized_signatory:
		generate_failure_page("Signatory details not found for this email.")

	if parent_doc_fields:
		return {**authorized_signatory, **parent_doc_fields}
	return authorized_signatory


def get_parent_document_fields(doctype, docname):
	doc = lock_document(doctype, docname)
	return {
		key: doc.get(key) for key in ("signed_document", "requested_print_format", "requested_letter_head")
	}


def get_signatory_details(doctype, docname):
	fields = (
		"name",
		"signatory",
		"signatory_name",
		"signatory_email",
		"sign_position",
		"signature_status",
		"reference_id",
		"last_tried",
		"select_page",
		"page_number",
		"page_level_coordinates",
		"customize_coordinates",
		"coordinates_reviewed",
	)
	return [
		{key: row.get(key) for key in fields}
		for row in frappe.get_doc(doctype, docname, for_update=True).get("signatory_detail", [])
	]


def validate_ongoing_review(signatory):
	if active_review(signatory):
		generate_failure_page(_("A signing session is active. Please try again after it finishes."))


def get_file_content(file_path):
	with open(file_path, "rb") as f:
		return f.read()


@frappe.whitelist()
def download_document_pdf(doctype, docname, signatory_details, print_format=None, letter_head=None):
	frappe.has_permission(doctype, "read", docname, throw=True)
	doc = frappe.get_doc(doctype, docname)
	if doc.get("signed_document"):
		return base64.b64encode(linked_file_content(doc)).decode("utf-8")

	# Use explicitly passed print format, or fall back to document's configured one
	pf = print_format
	lh = letter_head

	if not pf:
		try:
			pf = frappe.db.get_value(doctype, docname, "requested_print_format")
		except Exception:
			pf = None
	if not lh:
		try:
			lh = frappe.db.get_value(doctype, docname, "requested_letter_head")
		except Exception:
			lh = None

	html = frappe.get_print(doctype=doctype, name=docname, print_format=pf, letterhead=lh)
	return base64.b64encode(get_pdf(html)).decode("utf-8")


@frappe.whitelist()
def preview_before_signing(doctype, docname):
	"""Generate the actual document's PDF and return it along with all
	pending signatory positions so the frontend can render a visual
	verification overlay before sending signing requests."""
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "read", docname, throw=True)
	doc = frappe.get_doc(doctype, docname)
	signatories = doc.signatory_detail or []

	pending = [s for s in signatories if s.signature_status in ("Not Initiated", "Failure")]
	if not pending:
		return {"pending": [], "warnings": []}

	# Generate the actual PDF
	pdf_content = _get_document_pdf(doctype, docname)
	pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")
	pdf_info = _get_pdf_page_info(pdf_content)
	page_count = pdf_info["page_count"] if pdf_info else 0

	# Build signatory position data for the frontend
	signatory_positions = []
	warnings = (
		[] if pdf_info else [_("PDF page information is unavailable. Check the target page before sending.")]
	)

	for row in pending:
		name = row.signatory_name or row.signatory_email
		entry = {
			"child_name": row.name,
			"signatory_name": name,
			"sign_position": row.sign_position or "",
			"select_page": row.select_page or "",
			"page_number": row.page_number or "",
			"customize_coordinates": row.customize_coordinates or "",
			"coordinates_reviewed": row.get("coordinates_reviewed") or 0,
		}
		signatory_positions.append(entry)

		if row.sign_position == "Customize" and not row.get("coordinates_reviewed"):
			warnings.append(
				_(
					"{0}: Review and save this custom position again before sending. Its saved coordinate format needs review."
				).format(name)
			)

		# Detect issues
		if row.sign_position == "Customize" and not row.customize_coordinates:
			warnings.append(
				_("{0}: Sign position is 'Customize' but no coordinates have been set.").format(name)
			)

		if row.select_page == "SPECIFY":
			page_num = _safe_int(row.page_number, 0)
			if pdf_info and page_num > page_count:
				warnings.append(
					_("{0}: Targets page {1}, but this document only has {2} page(s).").format(
						name, page_num, page_count
					)
				)

	# Identical presets can collide too; do not silently show a clean preview.
	shared_presets = set()
	for index, row in enumerate(pending):
		for other in pending[index + 1 :]:
			if row.sign_position == "Customize" or row.sign_position != other.sign_position:
				continue
			pages = _selected_pages(row, page_count)
			other_pages = _selected_pages(other, page_count)
			if (
				pages
				and other_pages
				and pages.intersection(other_pages)
				and row.sign_position not in shared_presets
			):
				shared_presets.add(row.sign_position)
				warnings.append(
					_(
						"{0} and {1}: The same preset position targets a shared page. Check their placement."
					).format(
						row.signatory_name or row.signatory_email,
						other.signatory_name or other.signatory_email,
					)
				)

	# Overlap detection
	rects = []
	for row in pending:
		if row.sign_position == "Customize" and row.customize_coordinates:
			coords = _parse_coordinates(row.customize_coordinates)
			if coords:
				rects.append((row.signatory_name or row.signatory_email, *coords))

	for i, (na, ax, ay, aw, ah) in enumerate(rects):
		for nb, bx, by, bw, bh in rects[i + 1 :]:
			if _rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
				warnings.append(_("{0} and {1}: Signature positions overlap.").format(na, nb))

	return {
		"pdf_base64": pdf_base64,
		"page_count": page_count,
		"pending": signatory_positions,
		"warnings": warnings,
	}


def _get_document_pdf(doctype, docname):
	"""A missing signed attachment must never become an unsigned preview."""
	doc = frappe.get_doc(doctype, docname)
	if doc.get("signed_document"):
		return linked_file_content(doc)
	html = frappe.get_print(
		doctype=doctype,
		name=docname,
		print_format=doc.get("requested_print_format"),
		letterhead=doc.get("requested_letter_head"),
	)
	return get_pdf(html)


def _get_pdf_page_info(pdf_content):
	"""Extract page count and dimensions from PDF bytes."""
	try:
		from pypdf import PdfReader

		reader = PdfReader(io.BytesIO(pdf_content))
		pages = []
		for page in reader.pages:
			box = page.mediabox
			pages.append({"width": float(box.width), "height": float(box.height)})
		return {"page_count": len(pages), "pages": pages}
	except Exception:
		return None


def _selected_pages(row, page_count):
	if not page_count:
		return set()
	mode = row.get("select_page")
	if mode == "FIRST":
		return {1}
	if mode == "LAST":
		return {page_count}
	if mode == "ALL":
		return set(range(1, page_count + 1))
	if mode in {"EVEN", "ODD"}:
		return {page for page in range(1, page_count + 1) if page % 2 == (mode == "ODD")}
	if mode == "SPECIFY":
		return {
			number
			for part in str(row.get("page_number") or "").split(",")
			if 0 < (number := _safe_int(part)) <= page_count
		}
	return set()


def _parse_coordinates(coords_str):
	"""Parse 'x,y,w,h' string into a tuple of 4 floats, or None."""
	try:
		parts = [float(v.strip()) for v in coords_str.split(",")]
		if len(parts) == 4 and all(math.isfinite(value) for value in parts):
			if parts[0] >= 0 and parts[1] >= 0 and parts[2] > 0 and parts[3] > 0:
				return tuple(parts)
	except (ValueError, AttributeError):
		pass
	return None


def _safe_int(value, default=0):
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
	"""Check if two rectangles overlap (PDF coords: y from bottom)."""
	a_left, a_bottom, a_right, a_top = ax, ay - ah, ax + aw, ay
	b_left, b_bottom, b_right, b_top = bx, by - bh, bx + bw, by
	if a_right <= b_left or b_right <= a_left:
		return False
	if a_top <= b_bottom or b_top <= a_bottom:
		return False
	return True


@frappe.whitelist(methods=["POST"])
def fetch_emsigner_authorized_signatory(doctype, docname):
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "write", docname, throw=True)
	doc = lock_document(doctype, docname)
	if doc.get("signed_document") or any(
		row.signature_status not in {"Not Initiated", "Failure"} for row in doc.signatory_detail
	):
		frappe.throw(_("Signing has already started. Existing signatories cannot be reset."))
	settings = frappe.get_doc("emSigner Settings")
	config = next((row for row in settings.print_format if row.permitted_doctype == doctype), None)
	if config:
		doc.requested_print_format, doc.requested_letter_head = config.print_format, config.letter_head
	doc.set("signatory_detail", [])
	for row in settings.authorized_signatory:
		if row.permitted_doctype != doctype:
			continue
		doc.append(
			"signatory_detail",
			{
				"signatory": row.signatory,
				"signatory_name": row.signatory_name,
				"signatory_email": row.signatory_email,
				"sign_position": row.sign_position or (config and config.default_sign_position),
				"select_page": row.select_page or (config and config.default_select_page),
				"customize_coordinates": row.customize_coordinates
				or (config and config.default_customize_coordinates),
				"page_number": row.get("page_number") or "",
				"signature_status": "Not Initiated",
				"coordinates_reviewed": row.get("coordinates_reviewed") if row.customize_coordinates else 0,
			},
		)
	save_signing_document(doc)
