import urllib.parse
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime
from frappe.utils.password import get_decrypted_password

from emsigner.emsigner.utils.py.aes_ecb_cipher import AES_ECB_Cipher


@frappe.whitelist(allow_guest=True)
def decrypt_method():
	request_payload = frappe.request.data.decode("utf-8")
	if not isinstance(request_payload, str):
		raise ValueError("Expected a string for request payload")

	decrypt_payload(request_payload)


def decrypt_payload(request_payload):
	json_data = parse_request_payload(request_payload)

	reference_no = json_data.get("Referencenumber")
	return_value = json_data.get("Returnvalue")

	if not reference_no or not return_value:
		frappe.throw(_("Missing required fields: Referencenumber or Returnvalue"))

	decrypted_data = decrypt_return_value(return_value)

	if not is_valid_pdf(decrypted_data):
		frappe.throw(_("Decrypted data does not contain a valid PDF signature"))

	save_signed_pdf(reference_no, decrypted_data)

	frappe.local.response.update({"type": "redirect", "location": "/emsigner_success_page"})


def parse_request_payload(request_payload):
	parsed_data = urllib.parse.parse_qs(request_payload)
	return {key: value[0] for key, value in parsed_data.items()}


def decrypt_return_value(encrypted_value):
	session_key = get_session_key().encode("utf-8")
	aes_encrypt = AES_ECB_Cipher(key=session_key)

	decrypted_value = urllib.parse.unquote(encrypted_value)

	if len(decrypted_value) % 4 != 0:
		decrypted_value += "=" * (4 - len(decrypted_value) % 4)

	return aes_encrypt.decrypt(decrypted_value, decode=False)


def is_valid_pdf(data):
	return data.startswith(b"%PDF")


def save_signed_pdf(reference_no, content):
	signatory_log = get_signatory_details(reference_no)
	if not signatory_log:
		frappe.throw(_(f"No Signatory Log entry found for reference ID: {reference_no}"))

	validate_sign_expiry(signatory_log)

	doc = frappe.get_doc(
		{
			"doctype": "File",
			"content": content,
			"attached_to_doctype": signatory_log["parenttype"],
			"attached_to_name": signatory_log["parent"],
			"file_type": "PDF",
			"is_private": 0,
			"attached_to_field": "signed_document",
			"file_name": f"{reference_no}_signed_file.pdf",
			"folder": "Home/Attachments",
		}
	)
	doc.insert(ignore_permissions=True)

	update_signatory_details(signatory_log["name"], {"signature_status": "Completed"})
	update_file_url(signatory_log["parenttype"], signatory_log["parent"], doc.file_url)

	frappe.db.commit()


def get_session_key():
	return get_decrypted_password("emSigner Settings", "emSigner Settings", fieldname="session_key")


def get_signatory_details(reference_no):
	return frappe.db.get_value(
		"emSigner Signatory Detail",
		{"reference_id": reference_no},
		["parent", "parenttype", "last_tried", "name"],
		as_dict=True,
	)


def validate_sign_expiry(signatory):
	if signatory.get("last_tried"):
		time_difference = datetime.now() - get_datetime(signatory["last_tried"])
		if time_difference > timedelta(minutes=10):
			frappe.throw(_("There is an ongoing review. Kindly try after a few minutes."))
	else:
		frappe.throw(_("Something went wrong."))


def update_signatory_details(name, values):
	frappe.db.set_value("emSigner Signatory Detail", name, values)


def update_file_url(doctype, docname, url):
	frappe.db.set_value(doctype, docname, "signed_document", url)
