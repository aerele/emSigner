import base64
import binascii
import hashlib
import json
import os
import uuid

import frappe
from frappe.utils.password import get_decrypted_password
from frappe.utils.pdf import get_pdf

from emsigner.emsigner.utils.py.aes_ecb_cipher import AES_ECB_Cipher
from emsigner.emsigner.utils.py.rsa_encryption import RSAEncryption


@frappe.whitelist()
def get_emsigner_parameters(**args):
	authentication_mode = {"OTP": 1, "Biometric": 2, "Iris": 3, "Face": 4}
	settings_doc = frappe.get_doc("emSigner Settings")
	html = frappe.get_print(
		doctype=args["doctype_name"],
		name=args["document_name"],
		print_format=args.get("print_format"),
		letterhead=args.get("letter_head"),
	)

	ref_number = uuid.uuid4().hex
	data = {
		"Name": args.get("name"),
		"FileType": "PDF",
		"File": base64.b64encode(get_pdf(html)).decode("utf-8"),
		"PageNumber": args.get("page_number"),
		"PagelevelCoordinates": args.get("page_level_coordinates"),
		"CustomizeCoordinates": args.get("customize_coordinates"),
		"ReferenceNumber": ref_number,
		"AuthToken": get_decrypted_password(
			"emSigner Settings", "emSigner Settings", fieldname="authentication_token"
		),
		"SignatureType": 0,
		"SignatureMode": "3",
		"AuthenticationMode": authentication_mode[settings_doc.authentication_mode],
		"IsCosign": False,
		"SelectPage": args.get("select_page"),
		"SignaturePosition": args.get("signature_position"),
		"PreviewRequired": bool(settings_doc.preview_required),
		"Enableuploadsignature": bool(settings_doc.enable_upload_signature),
		"Enablefontsignature": bool(settings_doc.enable_font_signature),
		"EnableDrawSignature": bool(settings_doc.enable_draw_signature),
		"EnableeSignaturePad": bool(settings_doc.enable_esignature_pad),
		"Storetodb": bool(settings_doc.store_to_db),
		"EnableViewDocumentLink": bool(settings_doc.enable_view_document_link),
		"SUrl": f"{frappe.utils.get_url()}/api/method/emsigner.emsigner.api.emsigner_decrypt.decrypt_method",
		"FUrl": f"{frappe.utils.get_url()}/emsigner_furl",
		"CUrl": f"{frappe.utils.get_url()}/emsigner_curl",
		"IsCompressed": bool(settings_doc.is_compressed),
		"IsGSTN": bool(settings_doc.is_gstin),
		"IsGSTN3B": bool(settings_doc.is_gstn3b),
		"Reason": args.get("reason"),
	}

	json_data = json.dumps(data)

	session_key = generate_session_key(16)

	aes_cipher = AES_ECB_Cipher(key=session_key)
	encrypted_data = aes_cipher.encrypt(json_data).decode("utf-8")

	pubcertificate_path = (
		f"{frappe.get_doc('File', {'file_url': settings_doc.public_certificate}).get_full_path()}"
	)
	rsa_encryption = RSAEncryption(pubcertificate_path)
	encrypted_session_key = rsa_encryption.encrypt(session_key).decode("utf-8")

	hash_data = hashlib.sha256(json_data.encode("utf-8")).digest()
	encrypted_binary = aes_cipher.encrypt(hash_data, encode=False)
	encrypted_hash = base64.b64encode(encrypted_binary).decode("utf-8")

	html_wrapper = generate_html_wrapper(encrypted_session_key, encrypted_data, encrypted_hash)

	create_emsigner_log(
		args["doctype_name"],
		args["document_name"],
		session_key,
		encrypted_session_key,
		ref_number,
		encrypted_data,
		encrypted_hash,
	)

	return html_wrapper


def generate_session_key(key_size):
	session_key = os.urandom(16)
	session_key = binascii.hexlify(session_key).decode("utf-8").encode("utf-8")

	return session_key


def generate_html_wrapper(encrypted_session_key, encrypted_data, encrypted_hash):
	html_wrapper = f"""
	<html>
		<head>
			<script src="https://ajax.googleapis.com/ajax/libs/jquery/3.1.1/jquery.min.js"></script>
			<script>
				$(document).ready(function() {{ $('#signDocForm').submit(); }});
			</script>
		</head>
		<body>
			<table align="center">
				<tbody>
					<tr><td><strong>You are being redirected to emSigner portal</strong></td></tr>
					<tr><td><font color="blue">Please wait ...</font></td></tr>
					<tr><td>(Please do not press 'Refresh' or 'Back' button)</td></tr>
				</tbody>
			</table>
			<form id="signDocForm" name="signDocForm" method="post" action="https://demosignergateway.emsigner.com/eMsecure/V3_0/Index">
				<input type="hidden" name="Parameter1" id="Parameter1" value="{encrypted_session_key}">
				<input type="hidden" name="Parameter2" id="Parameter2" value="{encrypted_data}">
				<input type="hidden" name="Parameter3" id="Parameter3" value="{encrypted_hash}">
			</form>
		</body>
	</html>"""
	return html_wrapper


def create_emsigner_log(
	doctype,
	docname,
	session_key=None,
	encrypted_session_key=None,
	ref_number=None,
	encrypted_data=None,
	encrypted_hash=None,
):
	emsigner_log = frappe.new_doc("emSigner Log")
	emsigner_log.update(
		{
			"doctype_name": doctype,
			"document_name": docname,
			"session_key": session_key.decode("utf-8"),
			"encrypted_session_key": encrypted_session_key,
			"reference_id": ref_number,
			"encrypted_data": encrypted_data,
			"payload_json": encrypted_hash,
		}
	)

	emsigner_log.insert()
