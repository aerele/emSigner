import base64
import hashlib
import json

import frappe
from frappe import _

from emsigner.emsigner.utils.py.aes_ecb_cipher import AES_ECB_Cipher
from emsigner.emsigner.utils.py.rsa_encryption import RSAEncryption

AUTHENTICATION_MODES = {"OTP": 1, "Biometric": 2, "Iris": 3, "Face": 4}
SIGNATURE_MODES = {"Aadhar": 12, "dSign": 1, "eSign v3": 2, "eSign": 3}


def get_emsigner_parameters(**args):
	settings_doc = frappe.get_doc("emSigner Settings")
	validate_settings(settings_doc)

	ref_number = args.get("reference_id")
	if not ref_number:
		frappe.throw(_("Reference ID is required"), title=_("Validation Error"))

	sig_mode = settings_doc.signature_mode
	if sig_mode not in SIGNATURE_MODES:
		frappe.throw(
			_("Invalid Signature Mode: {0}. Expected one of: {1}").format(sig_mode, ", ".join(SIGNATURE_MODES)),
			title=_("Configuration Error"),
		)

	auth_mode = settings_doc.authentication_mode
	if auth_mode not in AUTHENTICATION_MODES:
		frappe.throw(
			_("Invalid Authentication Mode: {0}").format(auth_mode),
			title=_("Configuration Error"),
		)

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
		"SignatureMode": SIGNATURE_MODES[sig_mode],
		"AuthenticationMode": AUTHENTICATION_MODES[auth_mode],
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
		"FUrl": f"{frappe.utils.get_url()}/emsigner_failure_page?ref={ref_number}",
		"CUrl": f"{frappe.utils.get_url()}/emsigner_cancel_page?ref={ref_number}",
		"IsCompressed": bool(settings_doc.is_compressed),
		"IsGSTN": bool(settings_doc.is_gstin),
		"IsGSTN3B": bool(settings_doc.is_gstn3b),
		"Reason": args.get("reason"),
	}

	json_data = json.dumps(data)
	session_key = settings_doc.get_password("session_key").encode("utf-8")

	aes_cipher = AES_ECB_Cipher(key=session_key)
	encrypted_data = aes_cipher.encrypt(json_data).decode("utf-8")

	pubcertificate_path = get_certificate_path(settings_doc.public_certificate)
	rsa_encryption = RSAEncryption(pubcertificate_path)
	encrypted_session_key = rsa_encryption.encrypt(session_key).decode("utf-8")

	hash_data = hashlib.sha256(json_data.encode("utf-8")).digest()
	encrypted_binary = aes_cipher.encrypt(hash_data, encode=False)
	encrypted_hash = base64.b64encode(encrypted_binary).decode("utf-8")

	signing_data = {
		"encrypted_session_key": encrypted_session_key,
		"encrypted_data": encrypted_data,
		"encrypted_hash": encrypted_hash,
		"gateway_url": settings_doc.gateway_url
		or "https://signergateway.emsigner.com/eMsecure/V3_0/Index",
	}
	set_signing_data(ref_number, signing_data)

	redirect_url = f"/app/emudhra_signing_redirect?ref_number={ref_number}"
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = frappe.utils.get_url(redirect_url)


def validate_settings(settings_doc):
	missing = []
	if not settings_doc.authentication_token:
		missing.append(_("Authentication Token"))
	if not settings_doc.session_key:
		missing.append(_("Session Key"))
	if not settings_doc.public_certificate:
		missing.append(_("Public Certificate"))
	if not settings_doc.signature_mode:
		missing.append(_("Signature Mode"))
	if missing:
		frappe.throw(
			_("emSigner Settings incomplete. Please configure: {0}").format(", ".join(missing)),
			title=_("emSigner Configuration Required"),
		)


def get_certificate_path(file_url):
	try:
		return frappe.get_doc("File", {"file_url": file_url}).get_full_path()
	except frappe.DoesNotExistError:
		frappe.throw(
			_("Public certificate file not found. Please re-upload it in emSigner Settings."),
			title=_("Certificate Missing"),
		)


def set_signing_data(ref_number, signing_data):
	frappe.cache().set_value(f"emsigner_signing_data:{ref_number}", signing_data, expires_in_sec=600)


@frappe.whitelist(allow_guest=True)
def get_signing_data(ref_number):
	signing_data = frappe.cache().get_value(f"emsigner_signing_data:{ref_number}")
	if not signing_data:
		frappe.throw(_("Signing data not found or has expired. Please initiate a new signing request."))

	return signing_data
