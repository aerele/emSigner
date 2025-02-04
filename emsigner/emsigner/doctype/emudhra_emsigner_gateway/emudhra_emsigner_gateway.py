import os
import json
import frappe
import binascii
import hashlib
import uuid
import base64
import urllib.parse
from pathlib import Path
from base64 import b64encode, b64decode
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.Util.Padding import pad, unpad
from Crypto.PublicKey import RSA
from frappe.model.document import Document
from frappe.utils.pdf import get_pdf

class EmudhraemSignerGateway(Document):
	pass

authentication_mode =  {
		"OTP": 1,
		"Biometric": 2,
		"Iris": 3,
		"Face": 4
	}
class AES_ECB_Cipher:
	def __init__(self, key):
		self.key = key

	def encrypt(self, raw_data, encode=True):
		cipher = AES.new(self.key, AES.MODE_ECB)
		padded_data = pad(raw_data.encode() if isinstance(raw_data, str) else raw_data, AES.block_size)
		encrypted = cipher.encrypt(padded_data)
		return b64encode(encrypted) if encode else encrypted

	def decrypt(self, encrypted_data, decode=True):
		cipher = AES.new(self.key, AES.MODE_ECB)
		decoded_data = b64decode(encrypted_data)
		decrypted = cipher.decrypt(decoded_data)
		return unpad(decrypted, AES.block_size).decode() if decode else unpad(decrypted, AES.block_size)

class RSAEncryption:
	def __init__(self, pubcertificate_path):
		with open(pubcertificate_path, "r") as f:
			pub_key = f.read()
			self.cipher_rsa = PKCS1_v1_5.new(RSA.importKey(pub_key))

	def encrypt(self, raw_data):
		return b64encode(self.cipher_rsa.encrypt(raw_data))

@frappe.whitelist()
def get_emsigner_parameters(**args):
	settings_doc = frappe.get_doc("Emudhra emSigner Gateway")
	html = frappe.get_print(
		doctype = args["doctype_name"],
		name = args["document_name"],
		print_format = args.get("print_format"),
		letterhead = args.get("letter_head")
	)
	pdf = get_pdf(html)
	ref_number = uuid.uuid4().hex
	data = {
		"Name": args.get("name"),
		"FileType": "PDF",
		"File": base64.b64encode(pdf).decode('utf-8'),
		"ReferenceNumber": ref_number,
		"AuthToken": settings_doc.authentication_token,
		"SignatureType": 0,
		"SignatureMode": "3",
		"AuthenticationMode": authentication_mode[settings_doc.authentication_mode],
		"IsCosign": False,
		"SelectPage": settings_doc.select_page,
		"SignaturePosition": settings_doc.signature_position,
		"PreviewRequired": bool(settings_doc.preview_required),
		"Enableuploadsignature": bool(settings_doc.enable_upload_signature),
		"Enablefontsignature": bool(settings_doc.enable_font_signature),
		"EnableDrawSignature": bool(settings_doc.enable_draw_signature),
		"EnableeSignaturePad": bool(settings_doc.enable_esignature_pad),
		"Storetodb": bool(settings_doc.store_to_db),
		"EnableViewDocumentLink": bool(settings_doc.enable_view_document_link),
		"SUrl": f"{frappe.utils.get_url()}/api/method/emsigner.emsigner.doctype.emudhra_emsigner_gateway.emudhra_emsigner_gateway.decrypt_method",
		"FUrl": "https://test.com/emudhra/failure",
		"CUrl": "https://test.com/emudhra/cancel",
		"IsCompressed": bool(settings_doc.is_compressed),
		"IsGSTN": bool(settings_doc.is_gstin),
		"IsGSTN3B": bool(settings_doc.is_gstn3b)
	}

	json_data = json.dumps(data)
	session_key = os.urandom(16)
	session_key = binascii.hexlify(session_key).decode('utf-8').encode('utf-8')

	aes_cipher = AES_ECB_Cipher(key=session_key)
	encrypted_data = aes_cipher.encrypt(json_data).decode("utf-8")

	pubcertificate_path = f"{frappe.get_doc('File', {'file_url': settings_doc.public_certificate}).get_full_path()}"
	rsa_encryption = RSAEncryption(pubcertificate_path)
	encrypted_session_key = rsa_encryption.encrypt(session_key).decode("utf-8")

	hash_data = hashlib.sha256(json_data.encode("utf-8")).digest()
	encrypted_binary = aes_cipher.encrypt(hash_data, encode=False)
	encrypted_hash = base64.b64encode(encrypted_binary).decode("utf-8")

	html_wrapper = f'''
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
	</html>'''

	emsigner_log = frappe.new_doc("Emudhra emSigner log")
	emsigner_log.update({
		"doctype_name": args["doctype_name"],
		"document_name": args["document_name"],
		"session_key": session_key.decode('utf-8'),
		"encrypted_session_key": encrypted_session_key, 
		"reference_id": ref_number,
		"encrypted_data": encrypted_data, 
		"payload_json": encrypted_hash
	})
	emsigner_log.insert()

	return html_wrapper

@frappe.whitelist(allow_guest=True)
def decrypt_method():
	request_payload = frappe.request.data.decode('utf-8')
	if not isinstance(request_payload, str):
		raise ValueError("Expected a string for request payload")
	
	parsed_data = urllib.parse.parse_qs(request_payload)
	json_data = {key: value[0] for key, value in parsed_data.items()}

	reference_no = json_data.get('Referencenumber')
	return_value = json_data.get('Returnvalue')
	if not reference_no or not return_value:
		raise ValueError("Missing required fields: Referencenumber or Returnvalue")

	session_key = frappe.db.get_value("Emudhra emSigner log", {"reference_id": reference_no}, "session_key")
	if not session_key:
		raise ValueError(f"No session key found for reference number: {reference_no}")

	session_key = session_key.encode('utf-8')
	aes_encrypt = AES_ECB_Cipher(key=session_key)

	data = urllib.parse.unquote(return_value)
	if len(data) % 4 != 0:
		data += '=' * (4 - len(data) % 4)

	decrypt_data = aes_encrypt.decrypt(data, decode=False)

	if decrypt_data[:4] != b'%PDF':
		raise ValueError('Decrypted data does not contain a valid PDF signature')

	create_attachment(reference_no, decrypt_data)

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/emSignerParameters"

def create_attachment(reference_no, content):
	log = frappe.db.get_value("Emudhra emSigner log", {"reference_id": reference_no}, ["doctype_name", "document_name"], as_dict=True)
	doc = frappe.new_doc("File")
	doc.update(
		{
			"content": content,
			"attached_to_doctype": log["doctype_name"], 
			"attached_to_name": log["document_name"], 
			"file_type": "PDF", 
			"is_private": 0,
			"file_name": reference_no+"_signed_file.pdf",
			"folder": "Home/Attachments"
		})
	doc.insert(ignore_permissions=True)