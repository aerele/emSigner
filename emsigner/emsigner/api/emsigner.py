import base64
import hashlib
import json

import frappe

from emsigner.emsigner.utils.py.aes_ecb_cipher import AES_ECB_Cipher
from emsigner.emsigner.utils.py.rsa_encryption import RSAEncryption


def get_emsigner_parameters(**args):
	authentication_mode = {"OTP": 1, "Biometric": 2, "Iris": 3, "Face": 4}
	settings_doc = frappe.get_doc("emSigner Settings")

	ref_number = args["reference_id"]
	data = {
		"Name": args.get("signatory_name"),
		"FileType": "PDF",
		"File": args.get("file_content"),
		"PageNumber": args.get("page_number"),
		"PagelevelCoordinates": args.get("page_level_coordinates"),
		"CustomizeCoordinates": args.get("customize_coordinates"),
		"ReferenceNumber": ref_number,
		"AuthToken": settings_doc.get_password("authentication_token"),
		"SignatureType": 0,
		"SignatureMode": "3",
		"AuthenticationMode": authentication_mode[settings_doc.authentication_mode],
		"IsCosign": True,
		"SelectPage": args.get("select_page"),
		"SignaturePosition": args.get("signature_position"),
		"PreviewRequired": bool(settings_doc.preview_required),
		"Enableuploadsignature": bool(settings_doc.enable_upload_signature),
		"Enablefontsignature": bool(settings_doc.enable_font_signature),
		"EnableDrawSignature": bool(settings_doc.enable_draw_signature),
		"EnableeSignaturePad": bool(settings_doc.enable_esignature_pad),
		"Storetodb": bool(settings_doc.store_to_db),
		"SUrl": f"{frappe.utils.get_url()}/api/method/emsigner.emsigner.api.emsigner_decrypt.decrypt_method",
		"FUrl": f"{frappe.utils.get_url()}/emsigner_failure_page",
		"CUrl": f"{frappe.utils.get_url()}/emsigner_cancel_page",
		"IsCompressed": bool(settings_doc.is_compressed),
		"IsGSTN": bool(settings_doc.is_gstin),
		"IsGSTN3B": bool(settings_doc.is_gstn3b),
		"Reason": args.get("reason"),
	}

	json_data = json.dumps(data)
	session_key = settings_doc.get_password("session_key").encode("utf-8")

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

	signing_data = {
		"encrypted_session_key": encrypted_session_key,
		"encrypted_data": encrypted_data,
		"encrypted_hash": encrypted_hash,
	}
	set_signing_data(ref_number, signing_data)

	# Redirect to the eMudhra signing redirect page
	redirect_url = f"/app/emudhra_signing_redirect?ref_number={ref_number}"
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = frappe.utils.get_url(redirect_url)


def set_signing_data(ref_number, signing_data):
	frappe.cache().hset("signing_data_cache", ref_number, signing_data)


@frappe.whitelist(allow_guest=True)
def get_signing_data(ref_number):
	return frappe.cache().hget("signing_data_cache", ref_number)
