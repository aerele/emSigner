import urllib.parse

import frappe

from emsigner.emsigner.utils.py.aes_ecb_cipher import AES_ECB_Cipher


@frappe.whitelist(allow_guest=True)
def decrypt_method():
	request_payload = frappe.request.data.decode("utf-8")
	if not isinstance(request_payload, str):
		raise ValueError("Expected a string for request payload")

	parsed_data = urllib.parse.parse_qs(request_payload)
	json_data = {key: value[0] for key, value in parsed_data.items()}

	reference_no = json_data.get("Referencenumber")
	return_value = json_data.get("Returnvalue")
	if not reference_no or not return_value:
		raise ValueError("Missing required fields: Referencenumber or Returnvalue")

	session_key = frappe.db.get_value("emSigner Log", {"reference_id": reference_no}, "session_key")
	if not session_key:
		raise ValueError(f"No session key found for reference number: {reference_no}")

	session_key = session_key.encode("utf-8")
	aes_encrypt = AES_ECB_Cipher(key=session_key)

	data = urllib.parse.unquote(return_value)
	if len(data) % 4 != 0:
		data += "=" * (4 - len(data) % 4)

	decrypt_data = aes_encrypt.decrypt(data, decode=False)

	if decrypt_data[:4] != b"%PDF":
		raise ValueError("Decrypted data does not contain a valid PDF signature")

	create_attachment(reference_no, decrypt_data)

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/emSignerParameters"


def create_attachment(reference_no, content):
	log = frappe.db.get_value(
		"emSigner Log", {"reference_id": reference_no}, ["doctype_name", "document_name"], as_dict=True
	)
	doc = frappe.new_doc("File")
	doc.update(
		{
			"content": content,
			"attached_to_doctype": log["doctype_name"],
			"attached_to_name": log["document_name"],
			"file_type": "PDF",
			"is_private": 0,
			"file_name": reference_no + "_signed_file.pdf",
			"folder": "Home/Attachments",
		}
	)
	doc.insert(ignore_permissions=True)
