import base64
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import now_datetime
from werkzeug.wrappers import Response

from emsigner.emsigner.api import emsigner, emsigner_decrypt, make_sign, request_sign


class TestSigningSecurity(unittest.TestCase):
	def test_completed_signatory_cannot_start_again(self):
		rows = [
			frappe._dict(
				signatory_email="signer@example.invalid", reference_id="REF", signature_status="Completed"
			)
		]
		with (
			patch.object(make_sign, "get_signatory_details", return_value=rows),
			patch.object(make_sign, "get_parent_document_fields", return_value={}),
			self.assertRaises(frappe.ValidationError),
		):
			make_sign.verify_and_get_signatory("ToDo", "TEST-DOC", "signer@example.invalid", "REF")

	def test_other_active_signatory_blocks_a_parallel_start(self):
		rows = [
			frappe._dict(
				signatory_email="other@example.invalid",
				reference_id="OTHER",
				signature_status="Review In-Progress",
				last_tried=now_datetime(),
			),
			frappe._dict(
				signatory_email="signer@example.invalid",
				reference_id="REF",
				signature_status="Pending Review",
			),
		]
		with (
			patch.object(make_sign, "get_signatory_details", return_value=rows),
			patch.object(make_sign, "get_parent_document_fields", return_value={}),
			self.assertRaises(frappe.ValidationError),
		):
			make_sign.verify_and_get_signatory("ToDo", "TEST-DOC", "signer@example.invalid", "REF")

	def test_non_finite_and_invalid_rectangles_are_not_accepted(self):
		for text in ("NaN,2,3,4", "1,inf,3,4", "1,2,0,4", "1,2,-3,4", "-1,2,3,4"):
			with self.subTest(text=text):
				self.assertIsNone(make_sign._parse_coordinates(text))

	def test_download_ignores_a_client_selected_private_file(self):
		parent = frappe._dict(doctype="ToDo", name="TEST-DOC", signed_document="/private/files/actual.pdf")
		attachment = MagicMock()
		attachment.attached_to_doctype = "ToDo"
		attachment.attached_to_name = "TEST-DOC"
		attachment.get_content.return_value = b"%PDF actual"

		def get_doc(doctype, name=None, **kwargs):
			if doctype == "ToDo":
				return parent
			self.assertEqual(doctype, "File")
			self.assertEqual(name["file_url"], parent.signed_document)
			return attachment

		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_doc", side_effect=get_doc),
		):
			result = make_sign.download_document_pdf(
				"ToDo", "TEST-DOC", '{"signed_document":"/private/files/unrelated.pdf"}'
			)
		self.assertEqual(base64.b64decode(result), b"%PDF actual")
		attachment.check_permission.assert_called_once_with("read")

	def test_completed_callback_does_not_create_another_file(self):
		row = frappe._dict(
			name="TEST-SIGNER",
			parent="TEST-DOC",
			parenttype="ToDo",
			last_tried=now_datetime(),
			signature_status="Completed",
		)
		with (
			patch.object(emsigner_decrypt, "get_signatory_details", return_value=row),
			patch.object(frappe, "get_doc") as get_doc,
			self.assertRaises(frappe.ValidationError),
		):
			emsigner_decrypt.save_signed_pdf("REF", b"%PDF test")
		self.assertFalse(
			any(
				call.args and isinstance(call.args[0], dict) and call.args[0].get("doctype") == "File"
				for call in get_doc.call_args_list
			)
		)


class TestSigningBoundary(unittest.TestCase):
	def test_gateway_rejects_untrusted_or_cleartext_actions(self):
		for url in (
			"http://signergateway.emsigner.com/eMsecure/V3_0/Index",
			"https://evil.emsigner.com/eMsecure/V3_0/Index",
			"https://signergateway.emsigner.com.evil.invalid/eMsecure/V3_0/Index",
			"https://user@signergateway.emsigner.com/eMsecure/V3_0/Index",
			"https://signergateway.emsigner.com:bad/eMsecure/V3_0/Index",
			"https://signergateway.emsigner.com/other",
		):
			with self.subTest(url=url), self.assertRaises(frappe.ValidationError):
				emsigner.validate_gateway_url(url)

	def test_permission_denial_returns_no_file_content(self):
		with (
			patch.object(frappe, "has_permission", side_effect=frappe.PermissionError),
			patch.object(frappe, "get_doc") as get_doc,
			self.assertRaises(frappe.PermissionError),
		):
			make_sign.download_document_pdf("ToDo", "TEST-DOC", "{}")
		get_doc.assert_not_called()

	def test_a_missing_signed_file_never_falls_back_to_unsigned_print(self):
		doc = frappe._dict(doctype="ToDo", name="TEST-DOC", signed_document="/private/files/missing.pdf")
		with (
			patch.object(frappe, "get_doc", side_effect=[doc, frappe.DoesNotExistError()]),
			patch.object(frappe, "get_print") as print_doc,
			self.assertRaises(frappe.DoesNotExistError),
		):
			make_sign._get_document_pdf("ToDo", "TEST-DOC")
		print_doc.assert_not_called()


class TestFileApiVersions(unittest.TestCase):
	def test_v15_utf8_and_v16_binary_file_apis_preserve_exact_pdf_bytes(self):
		from emsigner.emsigner.api.signing_state import linked_file_content

		class V15File:
			attached_to_doctype, attached_to_name = "ToDo", "TEST-DOC"

			def check_permission(self, permission):
				assert permission == "read"

			def get_content(self):
				return "%PDF UTF-8 text"

		class V16File(V15File):
			def get_content(self, encodings=None):
				assert encodings == []
				return b"%PDF\xE2\xE3\xCF\xD3"

		parent = frappe._dict(doctype="ToDo", name="TEST-DOC", signed_document="/private/files/actual.pdf")
		for file_doc, expected in ((V15File(), b"%PDF UTF-8 text"), (V16File(), b"%PDF\xE2\xE3\xCF\xD3")):
			with self.subTest(version=type(file_doc).__name__), patch.object(
				frappe, "get_doc", return_value=file_doc
			):
				self.assertEqual(linked_file_content(parent), expected)
