import base64
import io
import json
from datetime import datetime, timedelta

import frappe
import jwt
from frappe import _
from frappe.utils import get_datetime, now
from frappe.utils.pdf import get_pdf

from emsigner.emsigner.api.emsigner import get_emsigner_parameters
from emsigner.emsigner.utils.py.throw_error import generate_failure_page

def _get_jwt_secret():
	"""Fetch JWT secret from settings. No module-level cache to avoid stale keys."""
	return frappe.utils.password.get_decrypted_password(
		"emSigner Settings", "emSigner Settings", fieldname="session_key"
	)


def validate_signing_doctype(doctype):
	"""Validate that the doctype is enabled for signing in emSigner Settings."""
	enabled = frappe.get_all(
		"emSigner Doctype", {"parent": "emSigner Settings"}, pluck="doctype_name"
	)
	if doctype not in enabled:
		generate_failure_page("This document type is not enabled for signing.")


@frappe.whitelist(allow_guest=True)
def make_sign():
	doctype = frappe.form_dict.get("doctype")
	docname = frappe.form_dict.get("docname")
	ref_id = frappe.form_dict.get("ref_id")
	token = frappe.form_dict.get("token")

	if not (doctype and docname and ref_id and token):
		generate_failure_page("Missing required parameters.")

	validate_signing_doctype(doctype)

	is_guest = frappe.session.user == "Guest"

	# Verify JWT token first — before elevating permissions
	signatory_details = _verify_signatory_as_guest(doctype, docname, ref_id, token) if is_guest \
		else verify_signatory(doctype, docname, ref_id, token)

	# For logged-in users, additionally verify document permission
	if not is_guest and not frappe.has_permission(doctype, "read"):
		generate_failure_page("You do not have permission to access this document.")

	# JWT verified — elevate permissions for guest to access document content
	if is_guest:
		frappe.flags.ignore_permissions = True
	try:
		initiate_signing_process(doctype, docname, ref_id, **signatory_details)
	finally:
		if is_guest:
			frappe.flags.ignore_permissions = False


def _verify_signatory_as_guest(doctype, docname, ref_id, token):
	"""Verify signatory for guest users with explicit ignore_permissions
	only on the signatory lookup, not globally."""
	frappe.flags.ignore_permissions = True
	try:
		return verify_signatory(doctype, docname, ref_id, token)
	finally:
		frappe.flags.ignore_permissions = False


def initiate_signing_process(doctype, docname, ref_id, **signatory_details):
	content = get_document_content(doctype, docname, signatory_details)
	send_for_signing(ref_id, content, signatory_details)
	update_signatory_status(doctype, docname, ref_id)


def get_document_content(doctype, docname, signatory_details):
	if signatory_details.get("signed_document"):
		file_url = signatory_details["signed_document"]
		try:
			file_path = frappe.get_doc("File", {"file_url": file_url}).get_full_path()
		except frappe.DoesNotExistError:
			frappe.throw(_("Signed document file not found: {0}").format(file_url))
		return get_file_content(file_path)

	pf = signatory_details.get("requested_print_format")
	lh = signatory_details.get("requested_letter_head")

	# Safely try reading from the document's custom fields
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
	return get_pdf(html)


def send_for_signing(ref_id, content, signatory_details):
	get_emsigner_parameters(
		reference_id=ref_id,
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


def update_signatory_status(doctype, docname, ref_id):
	frappe.db.set_value(
		"emSigner Signatory Detail",
		{"parenttype": doctype, "parent": docname, "reference_id": ref_id},
		{"signature_status": "Review In-Progress", "last_tried": now()},
	)


def verify_signatory(doctype, docname, ref_id, token):
	try:
		secret = _get_jwt_secret()
		payload = jwt.decode(token, secret, algorithms=["HS256"])
	except jwt.ExpiredSignatureError:
		generate_failure_page("The signing link has expired. Please request a new one.")
	except jwt.InvalidTokenError:
		generate_failure_page("Invalid signing link.")
	except Exception as e:
		frappe.log_error("emSigner JWT verification error", str(e))
		generate_failure_page("An error occurred while verifying the signing link.")

	email = payload.get("email")
	if not email:
		generate_failure_page("Invalid token: missing email.")

	ref_id_claim = payload.get("ref_id")
	if ref_id_claim and ref_id_claim != ref_id:
		generate_failure_page("Invalid token: reference mismatch.")

	return verify_and_get_signatory(doctype=doctype, docname=docname, email=email, ref_id=ref_id)


def verify_and_get_signatory(doctype, docname, email, ref_id):
	parent_doc_fields = get_parent_document_fields(doctype, docname)
	signatory_details = get_signatory_details(doctype, docname)

	authorized_signatory = None

	for row in signatory_details:
		if row["signatory_email"] == email and row["reference_id"] == ref_id:
			# Only validate ongoing review for the matched signatory
			validate_ongoing_review(row)
			authorized_signatory = row
			break

	if not authorized_signatory:
		generate_failure_page("Signatory details not found for this email.")

	if parent_doc_fields:
		return {**authorized_signatory, **parent_doc_fields}
	return authorized_signatory


def get_parent_document_fields(doctype, docname):
	try:
		return (
			frappe.db.get_value(
				doctype,
				docname,
				["signed_document", "requested_print_format", "requested_letter_head"],
				as_dict=True,
			)
			or {}
		)
	except Exception:
		return {}


def get_signatory_details(doctype, docname):
	return frappe.get_all(
		"emSigner Signatory Detail",
		filters={"parenttype": doctype, "parent": docname},
		fields=[
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
		],
	)


def validate_ongoing_review(signatory):
	if signatory["signature_status"] == "Review In-Progress" and signatory["last_tried"]:
		time_difference = datetime.now() - get_datetime(signatory["last_tried"])
		if time_difference < timedelta(minutes=10):
			generate_failure_page("There is an ongoing review for this signatory. Please try after a few minutes.")


def get_file_content(file_path):
	with open(file_path, "rb") as f:
		return f.read()


@frappe.whitelist()
def download_document_pdf(doctype, docname, signatory_details, print_format=None, letter_head=None):
	frappe.has_permission(doctype, "read", docname, throw=True)
	signatory_details = json.loads(signatory_details)

	if signatory_details.get("signed_document"):
		file_url = signatory_details["signed_document"]
		try:
			file_path = frappe.get_doc("File", {"file_url": file_url}).get_full_path()
		except frappe.DoesNotExistError:
			frappe.throw(_("Signed document file not found"))
		file_content = get_file_content(file_path)
		return base64.b64encode(file_content).decode("utf-8")

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

	pending = [
		s for s in signatories
		if s.signature_status in ("Not Initiated", "Failure")
	]
	if not pending:
		return {"pending": [], "warnings": []}

	# Generate the actual PDF
	pdf_content = _get_document_pdf(doctype, docname)
	pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")
	pdf_info = _get_pdf_page_info(pdf_content)
	page_count = pdf_info["page_count"] if pdf_info else 0

	# Build signatory position data for the frontend
	signatory_positions = []
	warnings = []

	for row in pending:
		name = row.signatory_name or row.signatory_email
		entry = {
			"child_name": row.name,
			"signatory_name": name,
			"sign_position": row.sign_position or "",
			"select_page": row.select_page or "",
			"page_number": row.page_number or "",
			"customize_coordinates": row.customize_coordinates or "",
		}
		signatory_positions.append(entry)

		# Detect issues
		if row.sign_position == "Customize" and not row.customize_coordinates:
			warnings.append(
				_("{0}: Sign position is 'Customize' but no coordinates have been set.").format(name)
			)

		if row.select_page == "SPECIFY":
			page_num = _safe_int(row.page_number, 0)
			if page_num > page_count:
				warnings.append(
					_("{0}: Targets page {1}, but this document only has {2} page(s).").format(
						name, page_num, page_count
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
		for nb, bx, by, bw, bh in rects[i + 1:]:
			if _rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
				warnings.append(
					_("{0} and {1}: Signature positions overlap.").format(na, nb)
				)

	return {
		"pdf_base64": pdf_base64,
		"page_count": page_count,
		"pending": signatory_positions,
		"warnings": warnings,
	}


def _get_document_pdf(doctype, docname):
	"""Generate and return raw PDF bytes for the document."""
	try:
		vals = frappe.db.get_value(
			doctype, docname,
			["signed_document", "requested_print_format", "requested_letter_head"],
			as_dict=True,
		)
		if vals and vals.get("signed_document"):
			file_path = frappe.get_doc("File", {"file_url": vals["signed_document"]}).get_full_path()
			return get_file_content(file_path)
		pf = vals.get("requested_print_format") if vals else None
		lh = vals.get("requested_letter_head") if vals else None
	except Exception:
		pf = lh = None

	html = frappe.get_print(doctype=doctype, name=docname, print_format=pf, letterhead=lh)
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


def _parse_coordinates(coords_str):
	"""Parse 'x,y,w,h' string into a tuple of 4 floats, or None."""
	try:
		parts = [float(v.strip()) for v in coords_str.split(",")]
		if len(parts) == 4:
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


@frappe.whitelist()
def fetch_emsigner_authorized_signatory(doctype, docname):
	validate_signing_doctype(doctype)
	frappe.has_permission(doctype, "write", docname, throw=True)
	settings_doc = frappe.get_doc("emSigner Settings")

	# Clear existing signatory detail rows
	frappe.db.delete("emSigner Signatory Detail", {"parent": docname, "parenttype": doctype})

	# Find matching print format config for defaults
	pf_config = None
	for pf in settings_doc.print_format:
		if pf.permitted_doctype == doctype:
			frappe.db.set_value(doctype, docname, {
				"requested_print_format": pf.print_format,
				"requested_letter_head": pf.letter_head,
			})
			pf_config = pf
			break

	idx = 0
	for signatory in settings_doc.authorized_signatory:
		if signatory.permitted_doctype == doctype:
			sign_position = signatory.sign_position
			select_page = signatory.select_page
			customize_coordinates = signatory.customize_coordinates

			# Apply per-print-format defaults if signatory doesn't have its own
			if pf_config:
				if not select_page and pf_config.default_select_page:
					select_page = pf_config.default_select_page
				if not sign_position and pf_config.default_sign_position:
					sign_position = pf_config.default_sign_position
				if not customize_coordinates and pf_config.default_customize_coordinates:
					customize_coordinates = pf_config.default_customize_coordinates

			idx += 1
			child = frappe.get_doc({
				"doctype": "emSigner Signatory Detail",
				"parent": docname,
				"parenttype": doctype,
				"parentfield": "signatory_detail",
				"idx": idx,
				"signatory": signatory.signatory,
				"signatory_name": signatory.signatory_name,
				"signatory_email": signatory.signatory_email,
				"select_page": select_page,
				"page_number": getattr(signatory, "page_number", None) or "",
				"sign_position": sign_position,
				"customize_coordinates": customize_coordinates,
				"signature_status": "Not Initiated",
			})
			child.db_insert()

	# Update parent's modified so client reload fetches fresh data
	frappe.db.set_value(doctype, docname, "modified", now())
