import base64
from datetime import datetime, timedelta

import frappe
import jwt
from frappe import _
from frappe.utils import get_datetime, now
from frappe.utils.pdf import get_pdf

from emsigner.emsigner.api.emsigner import get_emsigner_parameters


@frappe.whitelist(allow_guest=True)
def make_sign():
	doctype = frappe.form_dict.get("doctype")
	docname = frappe.form_dict.get("docname")
	ref_id = frappe.form_dict.get("ref_id")
	token = frappe.form_dict.get("token")

	if not (doctype and docname and ref_id and token):
		frappe.throw("Missing required parameters.", title="Validation Error")

	# Verify signatory and get details
	signatory_details = verify_signatory(doctype, docname, ref_id, token)

	initiate_signing_process(doctype, docname, ref_id, **signatory_details)


def initiate_signing_process(doctype, docname, ref_id, **signatory_details):
	content = get_document_content(doctype, docname, signatory_details)
	send_for_signing(ref_id, content, signatory_details)
	update_signatory_status(doctype, docname, ref_id)


def get_document_content(doctype, docname, signatory_details):
	if signatory_details.get("signed_document"):
		file_path = frappe.get_doc("File", {"file_url": signatory_details["signed_document"]}).get_full_path()
		return get_file_content(file_path)

	html = frappe.get_print(
		doctype=doctype,
		name=docname,
		print_format=signatory_details.get("requested_print_format", "Standard"),
		letterhead=signatory_details.get("requested_letter_head"),
	)
	return get_pdf(html)


def send_for_signing(ref_id, content, signatory_details):
	get_emsigner_parameters(
		reference_id=ref_id,
		signatory_name=signatory_details["signatory_name"],
		file_content=base64.b64encode(content).decode("utf-8"),
		select_page=signatory_details["select_page"],
		page_number=signatory_details["page_number"],
		page_level_coordinates=signatory_details["page_level_coordinates"],
		signature_position=signatory_details["sign_position"],
		customize_coordinates=signatory_details["customize_coordinates"],
		reason="Test",
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
		frappe.throw(_("The token has expired."))
	except jwt.InvalidTokenError:
		frappe.throw(_("Invalid token."))
	except Exception as e:
		frappe.throw(_("An error occurred while verifying signatory: {0}").format(str(e)))


def verify_and_get_signatory(doctype, docname, email):
	parent_doc_fields = get_parent_document_fields(doctype, docname)
	signatory_details = get_signatory_details(doctype, docname)

	authorized_signatory = None

	for row in signatory_details:
		validate_ongoing_review(row)
		if row["signatory_email"] == email:
			authorized_signatory = row

	if not authorized_signatory:
		frappe.throw(_("Signatory details not found."))

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
		if time_difference < timedelta(minutes=5):
			frappe.throw(_("There is an ongoing review. Kindly try after a few minutes."))


def get_file_content(file_path):
	with open(file_path) as f:
		return f.read()
