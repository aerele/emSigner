import base64
import json
from datetime import datetime, timedelta

import frappe
import jwt
from frappe import _
from frappe.utils import get_datetime, now
from frappe.utils.pdf import get_pdf

from emsigner.emsigner.api.emsigner import get_emsigner_parameters
from emsigner.emsigner.utils.py.throw_error import generate_failure_page


@frappe.whitelist(allow_guest=True)
def make_sign():
	doctype = frappe.form_dict.get("doctype")
	docname = frappe.form_dict.get("docname")
	ref_id = frappe.form_dict.get("ref_id")
	token = frappe.form_dict.get("token")

	check_user_login_and_permission(doctype)
	if not (doctype and docname and ref_id and token):
		frappe.throw("Missing required parameters.", title="Validation Error")

	# Verify signatory and get details
	signatory_details = verify_signatory(doctype, docname, ref_id, token)

	initiate_signing_process(doctype, docname, ref_id, **signatory_details)


def check_user_login_and_permission(doctype):
	logged_in_user = None

	if not logged_in_user:
		generate_failure_page("There is an ongoing review. Kindly try after a few minutes.")

	if not frappe.has_permission(doctype, "read"):
		generate_failure_page("No permission")


def initiate_signing_process(doctype, docname, ref_id, **signatory_details):
	content = get_document_content(doctype, docname, signatory_details)
	send_for_signing(ref_id, content, signatory_details)
	update_signatory_status(doctype, docname, ref_id)


def get_document_content(doctype, docname, signatory_details):
	if signatory_details.get("signed_document"):
		file_path = frappe.get_doc("File", {"file_url": signatory_details["signed_document"]}).get_full_path()
		return get_file_content(file_path)
	else:
		html = frappe.get_print(
			doctype=doctype,
			name=docname,
			print_format=frappe.db.get_value(doctype, docname, "requested_print_format"),
			letterhead=frappe.db.get_value(doctype, docname, "requested_letter_head"),
		)
		return get_pdf(html)


def send_for_signing(ref_id, content, signatory_details):
	get_emsigner_parameters(
		reference_id=ref_id,
		signatory_name=signatory_details["signatory_name"],
		file_content=base64.b64encode(content).decode("utf-8"),
		select_page=signatory_details["select_page"] or "",
		page_number=signatory_details["page_number"] or "",
		page_level_coordinates=signatory_details["page_level_coordinates"] or "",
		signature_position=signatory_details["sign_position"] or "",
		customize_coordinates=signatory_details["customize_coordinates"]
		if signatory_details["sign_position"] == "Customize"
		else "",
		reason="",
	)


def update_signatory_status(doctype, docname, ref_id):
	"""Updates the signatory status to 'Review In-Progress' and logs the timestamp."""

	frappe.db.set_value(
		"emSigner Signatory Detail",
		{"parenttype": doctype, "parent": docname, "reference_id": ref_id},
		{"signature_status": "Review In-Progress", "last_tried": now()},
	)
	frappe.db.commit()


def verify_signatory(doctype, docname, ref_id, token):
	try:
		payload = jwt.decode(token, ref_id, algorithms=["HS256"])
		email = payload.get("email")
		return verify_and_get_signatory(doctype=doctype, docname=docname, email=email)

	except jwt.ExpiredSignatureError:
		generate_failure_page("The token has expired.")
	except jwt.InvalidTokenError:
		generate_failure_page("Invalid token.")
	except Exception as e:
		generate_failure_page("An error occurred while verifying signatory: {0}").format(str(e))


def verify_and_get_signatory(doctype, docname, email):
	parent_doc_fields = get_parent_document_fields(doctype, docname)
	signatory_details = get_signatory_details(doctype, docname)

	authorized_signatory = None

	for row in signatory_details:
		validate_ongoing_review(row)
		if row["signatory_email"] == email:
			authorized_signatory = row

	if not authorized_signatory:
		generate_failure_page("Signatory details not found.")

	return {**authorized_signatory, **parent_doc_fields} if parent_doc_fields else authorized_signatory


def get_parent_document_fields(doctype, docname):
	return (
		frappe.db.get_value(
			doctype,
			docname,
			["signed_document", "requested_print_format", "requested_letter_head"],
			as_dict=True,
		)
		or {}
	)


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
			generate_failure_page("There is an ongoing review. Kindly try after a few minutes.")


def get_file_content(file_path):
	with open(file_path, "rb") as f:
		return f.read()


@frappe.whitelist()
def download_document_pdf(doctype, docname, signatory_details):
	signatory_details = json.loads(signatory_details)

	if signatory_details.get("signed_document"):
		# Get file content and encode it to Base64
		file_path = frappe.get_doc("File", {"file_url": signatory_details["signed_document"]}).get_full_path()
		file_content, _ = get_file_content(file_path)  # Unpack tuple (content, type)
		return base64.b64encode(file_content).decode("utf-8")  # Return Base64-encoded content
	else:
		# Generate PDF from HTML and encode to Base64
		html = frappe.get_print(
			doctype=doctype,
			name=docname,
			print_format=frappe.db.get_value(doctype, docname, "requested_print_format"),
			letterhead=frappe.db.get_value(doctype, docname, "requested_letter_head"),
		)
		return base64.b64encode(get_pdf(html)).decode("utf-8")  # Return Base64-encoded content


@frappe.whitelist()
def fetch_emsigner_authorized_signatory(doctype, docname):
	settings_doc = frappe.get_doc("emSigner Settings")
	doc = frappe.get_doc(doctype, docname)
	doc.signatory_detail = []
	for signatory in settings_doc.authorized_signatory:
		if signatory.permitted_doctype == doctype:
			doc.append(
				"signatory_detail",
				{
					"signatory": signatory.signatory,
					"signatory_name": signatory.signatory_name,
					"signatory_email": signatory.signatory_email,
					"select_page": signatory.select_page,
					"sign_position": signatory.sign_position,
					"customize_coordinates": signatory.customize_coordinates,
				},
			)
	for print_format in settings_doc.print_format:
		if print_format.permitted_doctype == doctype:
			doc.requested_print_format = print_format.print_format
			doc.requested_letter_head = print_format.letter_head
			break
	doc.save()
	return
