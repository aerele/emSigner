"""Native transaction tests. Use only a disposable Frappe test site."""

import base64
import contextvars
import io
import json
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import frappe
import jwt
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password, set_encrypted_password
from pypdf import PdfWriter
from werkzeug.wrappers import Request, Response

from emsigner.emsigner.api import emsigner, emsigner_decrypt, make_sign, request_sign
from emsigner.emsigner.api.signing_state import lock_document
from emsigner.emsigner.utils.py.aes_ecb_cipher import AES_ECB_Cipher
from emsigner.patches import preserve_signing_settings

TEST_DT = "emSigner Test Document"


def ensure_test_doctype():
	if frappe.db.exists("DocType", TEST_DT):
		return
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": TEST_DT,
			"module": "Core",
			"custom": 1,
			"track_changes": 1,
			"autoname": "hash",
			"fields": [
				{"fieldname": "description", "fieldtype": "Data", "label": "Description"},
				{
					"fieldname": "signed_document",
					"fieldtype": "Attach",
					"label": "Signed Document",
					"allow_on_submit": 1,
				},
				{
					"fieldname": "requested_print_format",
					"fieldtype": "Link",
					"options": "Print Format",
					"label": "Print Format",
				},
				{
					"fieldname": "requested_letter_head",
					"fieldtype": "Link",
					"options": "Letter Head",
					"label": "Letter Head",
				},
				{
					"fieldname": "signatory_detail",
					"fieldtype": "Table",
					"options": "emSigner Signatory Detail",
					"label": "Signatories",
					"allow_on_submit": 1,
				},
			],
			"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()


def pdf_bytes():
	writer = PdfWriter()
	writer.add_blank_page(width=595, height=842)
	out = io.BytesIO()
	writer.write(out)
	return out.getvalue() + b"\n% test " + uuid.uuid4().hex.encode()


class TestSigningFlow(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		ensure_test_doctype()

	def setUp(self):
		frappe.set_user("Administrator")
		self.site, self.sites_path = frappe.local.site, frappe.local.sites_path
		self.old_singles = frappe.db.sql(
			"select * from tabSingles where doctype=%s", "emSigner Settings", as_dict=True
		)
		self.old_auth = frappe.db.sql(
			"select * from __Auth where doctype=%s and name=%s",
			("emSigner Settings", "emSigner Settings"),
			as_dict=True,
		)
		self.old_doctypes = frappe.get_all(
			"emSigner Doctype", filters={"parent": "emSigner Settings"}, fields=["*"]
		)
		frappe.db.delete("emSigner Doctype", {"parent": "emSigner Settings"})
		self.doc = frappe.get_doc({"doctype": TEST_DT, "description": "Synthetic signing test"})
		for i in range(2):
			self.doc.append(
				"signatory_detail",
				{
					"signatory_name": f"Synthetic signer {i}",
					"signatory_email": f"signer{i}@example.invalid",
					"signature_status": "Pending Review",
					"reference_id": uuid.uuid4().hex,
					"sign_position": "Top-Left",
					"select_page": "FIRST",
				},
			)
		self.doc.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "emSigner Doctype",
				"parent": "emSigner Settings",
				"parenttype": "emSigner Settings",
				"parentfield": "doctypes",
				"doctype_name": TEST_DT,
			}
		).db_insert()
		frappe.db.set_single_value(
			"emSigner Settings",
			{
				"name": "emSigner Settings",
				"doctype": "emSigner Settings",
				"document_type": "PDF",
				"gateway_url": emsigner.DEMO_GATEWAY,
				"session_key": "********",
				"signing_secret": "********",
				"authentication_token": "********",
				"authentication_mode": "OTP",
				"signature_mode": "dSign",
				"public_certificate": "/private/files/synthetic.pem",
				"legacy_links_until": now_datetime() + timedelta(days=7),
			},
		)
		for field, value in (
			("session_key", "S" * 32),
			("signing_secret", "L" * 48),
			("authentication_token", "SYNTHETIC"),
		):
			set_encrypted_password("emSigner Settings", "emSigner Settings", value, fieldname=field)
		self.links = [
			request_sign.generate_request_link(TEST_DT, self.doc.name, row.signatory_email, row.reference_id)
			for row in self.doc.signatory_detail
		]
		frappe.db.commit()
		self.source_pdf = pdf_bytes()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for file_name in frappe.get_all(
			"File", filters={"attached_to_doctype": TEST_DT, "attached_to_name": self.doc.name}, pluck="name"
		):
			frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
		if frappe.db.exists(TEST_DT, self.doc.name):
			frappe.delete_doc(TEST_DT, self.doc.name, ignore_permissions=True, force=True)
		frappe.db.delete(
			"__Auth",
			{
				"doctype": "emSigner Signatory Detail",
				"name": ["in", [row.name for row in self.doc.signatory_detail]],
			},
		)
		frappe.db.delete("Singles", {"doctype": "emSigner Settings"})
		frappe.db.delete("__Auth", {"doctype": "emSigner Settings", "name": "emSigner Settings"})
		for table, rows in (("Singles", self.old_singles), ("__Auth", self.old_auth)):
			for row in rows:
				dt = frappe.qb.DocType(table)
				frappe.qb.into(dt).columns(*row).insert(*row.values()).run()
		frappe.db.delete("emSigner Doctype", {"parent": "emSigner Settings"})
		for row in self.old_doctypes:
			frappe.get_doc({"doctype": "emSigner Doctype", **row}).db_insert()
		frappe.db.commit()
		frappe.flags.commit = False

	def request(self, method, *, link=None, body=None, operation=None):
		"""A new native Frappe context and connection for every HTTP transaction."""

		def work():
			frappe.init(site=self.site, sites_path=self.sites_path, force=True)
			frappe.connect()
			if os.environ.get("EMSIGNER_TEST_ISOLATION") == "REPEATABLE READ":
				frappe.db.commit()
				frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
			frappe.local.module_app["emsigner"] = "emsigner"
			frappe.set_user("Guest")
			frappe.flags.in_test = True
			frappe.in_test = True
			frappe.local.request = Request.from_values(
				path="/api/method/emsigner.test",
				method=method,
				data=body,
				query_string=urlsplit(link or "").query,
				content_type="application/x-www-form-urlencoded",
			)
			from frappe.app import make_form_dict

			make_form_dict(frappe.local.request)
			try:
				if operation:
					result = operation()
				else:
					result = make_sign.make_sign() if method == "GET" else emsigner_decrypt.decrypt_method()
				from frappe.app import sync_database

				sync_database()
				return result
			finally:
				frappe.db.rollback()
				frappe.destroy()

		return contextvars.Context().run(work)

	def start(self, index=0):
		with (
			patch.object(make_sign, "get_pdf", return_value=self.source_pdf),
			patch.object(frappe, "get_print", return_value="synthetic"),
			patch.object(emsigner, "get_certificate_path", return_value="synthetic.pem"),
			patch.object(emsigner, "RSAEncryption") as rsa,
		):
			rsa.return_value.encrypt.return_value = b"synthetic-encrypted-key"
			return self.request("GET", link=self.links[index])

	def read_doc(self):
		frappe.db.rollback()  # clear any older repeatable-read snapshot
		return frappe.get_doc(TEST_DT, self.doc.name)

	def callback(self, row, content=None):
		key = base64.b64decode(
			get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		)
		body = urlencode(
			{
				"Referencenumber": row.signing_reference,
				"ReturnStatus": "Success",
				"Returnvalue": AES_ECB_Cipher(key).encrypt(content or self.source_pdf).decode(),
			}
		)
		return self.request("POST", body=body)

	def test_guest_get_returns_form_and_commits_its_session(self):
		response = self.start()
		self.assertEqual(response.status_code, 200)
		self.assertIn('name="Parameter1"', response.get_data(as_text=True))
		self.assertIn('name="Parameter2"', response.get_data(as_text=True))
		self.assertNotIn("/app/", response.get_data(as_text=True))
		self.assertNotIn("Location", response.headers)
		self.assertEqual(response.headers["Cache-Control"], "no-store")
		row = self.read_doc().signatory_detail[0]
		self.assertEqual(row.signature_status, "Review In-Progress")
		self.assertLessEqual(len(row.signing_reference), 20)
		self.assertTrue(row.last_tried)
		self.assertNotEqual(row.reference_id, row.signing_reference)

	def test_bad_token_is_a_safe_html_failure_without_state_change(self):
		response = self.request("GET", link=self.links[0] + "INVALID")
		self.assertEqual(response.status_code, 400)
		self.assertIn("Signing could not continue", response.get_data(as_text=True))
		self.assertNotIn("Server Error", response.get_data(as_text=True))
		self.assertEqual(self.read_doc().signatory_detail[0].signature_status, "Pending Review")

	def test_callback_is_single_use_and_next_signer_reads_signed_content(self):
		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		body_key = base64.b64decode(
			get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		)
		signed = pdf_bytes()
		body = urlencode(
			{
				"Referencenumber": row.signing_reference,
				"Returnvalue": AES_ECB_Cipher(body_key).encrypt(signed).decode(),
			}
		)
		self.assertEqual(self.request("POST", body=body).status_code, 303)
		self.assertEqual(self.request("POST", body=body).status_code, 400)
		doc = self.read_doc()
		self.assertEqual(doc.signatory_detail[0].signature_status, "Completed")
		self.assertEqual(
			frappe.db.count("File", {"attached_to_doctype": TEST_DT, "attached_to_name": doc.name}), 1
		)
		self.assertEqual(self.start(0).status_code, 400)
		with patch.object(
			make_sign, "get_emsigner_parameters", return_value=Response("synthetic")
		) as gateway:
			self.assertEqual(self.request("GET", link=self.links[1]).status_code, 200)
			self.assertEqual(base64.b64decode(gateway.call_args.kwargs["file_content"]), signed)

	def test_parallel_starts_allow_one_active_document_session(self):
		barrier = threading.Barrier(2)

		def begin(index):
			barrier.wait(timeout=5)
			return self.request("GET", link=self.links[index]).status_code

		with (
			patch.object(make_sign, "get_document_content", return_value=self.source_pdf),
			patch.object(
				make_sign, "get_emsigner_parameters", side_effect=lambda **kwargs: Response("synthetic")
			),
			ThreadPoolExecutor(max_workers=2) as pool,
		):
			statuses = list(pool.map(begin, (0, 1)))
		self.assertEqual(sorted(statuses), [200, 400])
		self.assertEqual(
			sum(row.signature_status == "Review In-Progress" for row in self.read_doc().signatory_detail), 1
		)

	def test_late_callback_cannot_complete_a_replacement_attempt(self):
		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		key = base64.b64decode(
			get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		)
		old_body = urlencode(
			{
				"Referencenumber": row.signing_reference,
				"Returnvalue": AES_ECB_Cipher(key).encrypt(self.source_pdf).decode(),
			}
		)
		frappe.db.set_value(
			"emSigner Signatory Detail", row.name, "last_tried", now_datetime() - timedelta(minutes=11)
		)
		frappe.db.commit()
		self.assertEqual(self.start().status_code, 200)
		self.assertNotEqual(self.read_doc().signatory_detail[0].signing_reference, row.signing_reference)
		self.assertEqual(self.request("POST", body=old_body).status_code, 400)
		doc = self.read_doc()
		self.assertFalse(doc.signed_document)
		self.assertEqual(doc.signatory_detail[0].signature_status, "Review In-Progress")
		self.assertEqual(
			frappe.db.count("File", {"attached_to_doctype": TEST_DT, "attached_to_name": doc.name}), 0
		)

	def test_refresh_does_not_delete_a_completed_signatory(self):
		frappe.db.set_value(
			"emSigner Signatory Detail", self.doc.signatory_detail[0].name, "signature_status", "Completed"
		)
		frappe.db.commit()
		before = [row.name for row in self.read_doc().signatory_detail]
		with self.assertRaises(frappe.ValidationError):
			make_sign.fetch_emsigner_authorized_signatory(TEST_DT, self.doc.name)
		self.assertEqual([row.name for row in self.read_doc().signatory_detail], before)

	def test_migration_keeps_demo_secret_and_fixed_legacy_cutoff(self):
		frappe.db.set_single_value("emSigner Settings", "gateway_url", "")
		with patch.object(preserve_signing_settings, "make_custom_fields"):
			preserve_signing_settings.execute()
		secret = get_decrypted_password("emSigner Settings", "emSigner Settings", fieldname="signing_secret")
		until = frappe.db.get_single_value("emSigner Settings", "legacy_links_until")
		self.assertEqual(
			frappe.db.get_single_value("emSigner Settings", "gateway_url"), emsigner.DEMO_GATEWAY
		)
		with patch.object(preserve_signing_settings, "make_custom_fields"):
			preserve_signing_settings.execute()
		self.assertEqual(
			get_decrypted_password("emSigner Settings", "emSigner Settings", fieldname="signing_secret"),
			secret,
		)
		self.assertEqual(frappe.db.get_single_value("emSigner Settings", "legacy_links_until"), until)

	def test_parallel_callbacks_create_one_file(self):
		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		key = base64.b64decode(
			get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		)
		body = urlencode(
			{
				"Referencenumber": row.signing_reference,
				"Returnvalue": AES_ECB_Cipher(key).encrypt(self.source_pdf).decode(),
			}
		)
		barrier = threading.Barrier(2)

		def finish(_):
			barrier.wait(timeout=5)
			return self.request("POST", body=body).status_code

		with ThreadPoolExecutor(max_workers=2) as pool:
			self.assertEqual(sorted(pool.map(finish, (0, 1))), [303, 400])
		self.assertEqual(self.read_doc().signatory_detail[0].signature_status, "Completed")
		self.assertEqual(
			frappe.db.count("File", {"attached_to_doctype": TEST_DT, "attached_to_name": self.doc.name}), 1
		)

	def test_two_email_requests_keep_the_first_links_and_send_once(self):
		for row in self.doc.signatory_detail:
			frappe.db.set_value("emSigner Signatory Detail", row.name, "signature_status", "Not Initiated")
		frappe.db.commit()
		barrier = threading.Barrier(2)

		def send(_):
			barrier.wait(timeout=5)

			def operation():
				frappe.set_user("Administrator")
				request_sign.send_email_request(TEST_DT, self.doc.name)
				return Response("sent")

			return self.request("POST", operation=operation)

		with (
			patch.object(request_sign, "send_email") as send_email,
			ThreadPoolExecutor(max_workers=2) as pool,
		):
			self.assertEqual([response.status_code for response in pool.map(send, (0, 1))], [200, 200])
			self.assertEqual(send_email.call_count, 2)
		self.assertTrue(
			all(row.signature_status == "Pending Review" for row in self.read_doc().signatory_detail)
		)

	def test_active_reminder_does_not_rotate_ref_and_retry_is_throttled(self):
		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		with patch.object(request_sign, "send_email") as email, self.assertRaises(frappe.ValidationError):
			request_sign.resend_reminder(TEST_DT, self.doc.name, row.name)
		email.assert_not_called()
		self.assertEqual(self.read_doc().signatory_detail[0].reference_id, row.reference_id)
		frappe.db.set_value(
			"emSigner Signatory Detail", row.name, "last_tried", now_datetime() - timedelta(minutes=11)
		)
		frappe.db.commit()
		with patch.object(request_sign, "send_email") as email:
			request_sign.resend_reminder(TEST_DT, self.doc.name, row.name)
			frappe.db.commit()
			new_ref = self.read_doc().signatory_detail[0].reference_id
			self.assertNotEqual(new_ref, row.reference_id)
			with self.assertRaises(frappe.ValidationError):
				request_sign.resend_reminder(TEST_DT, self.doc.name, row.name)
			self.assertEqual(email.call_count, 1)
		self.assertEqual(self.read_doc().signatory_detail[0].reference_id, new_ref)

	def test_legacy_link_overlap_expires_and_new_tokens_bind_the_document(self):
		row = self.doc.signatory_detail[0]
		from datetime import datetime, timezone

		claims = {"email": row.signatory_email, "exp": datetime.now(timezone.utc) + timedelta(days=1)}
		for secret in (row.reference_id, "S" * 32):
			token = jwt.encode(claims, secret, algorithm="HS256")
			self.assertEqual(
				make_sign._decode_signing_token(token, TEST_DT, self.doc.name, row.reference_id)["email"],
				row.signatory_email,
			)
		frappe.db.set_single_value(
			"emSigner Settings", "legacy_links_until", now_datetime() - timedelta(seconds=1)
		)
		with self.assertRaises(jwt.InvalidTokenError):
			make_sign._decode_signing_token(token, TEST_DT, self.doc.name, row.reference_id)
		new_token = parse_qs(urlsplit(self.links[0]).query)["token"][0]
		self.assertEqual(
			make_sign._decode_signing_token(new_token, TEST_DT, self.doc.name, row.reference_id)["purpose"],
			"emsigner-sign",
		)
		with self.assertRaises(jwt.InvalidTokenError):
			make_sign._decode_signing_token(new_token, TEST_DT, "OTHER-DOC", row.reference_id)

	def test_preset_page_edit_saves_and_nan_edit_changes_nothing(self):
		row = self.doc.signatory_detail[0]
		frappe.db.set_value("emSigner Signatory Detail", row.name, "signature_status", "Not Initiated")
		frappe.db.commit()
		request_sign.update_coordinates_value(
			"emSigner Signatory Detail", row.name, select_page="SPECIFY", page_number=3
		)
		frappe.db.commit()
		self.assertEqual(self.read_doc().signatory_detail[0].select_page, "SPECIFY")
		with self.assertRaises(frappe.ValidationError):
			request_sign.update_coordinates_value(
				"emSigner Signatory Detail", row.name, "NaN,2,3,4", sign_position="Customize"
			)
		frappe.db.rollback()
		row = self.read_doc().signatory_detail[0]
		self.assertEqual(row.sign_position, "Top-Left")
		self.assertEqual(row.page_number, "3")

	def test_expired_session_cleanup_removes_key_and_preserves_active_sibling(self):
		from emsigner.emsigner.api.signing_state import cleanup_expired_sessions

		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		frappe.db.set_value(
			"emSigner Signatory Detail", row.name, "last_tried", now_datetime() - timedelta(minutes=11)
		)
		frappe.db.commit()
		self.assertEqual(self.start(1).status_code, 200)
		active = self.read_doc().signatory_detail[1]
		cleanup_expired_sessions()
		frappe.db.commit()
		doc = self.read_doc()
		self.assertEqual(doc.signatory_detail[0].signature_status, "Failure")
		self.assertIsNone(
			get_decrypted_password(
				"emSigner Signatory Detail", row.name, fieldname="callback_key", raise_exception=False
			)
		)
		self.assertEqual(doc.signatory_detail[1].signing_reference, active.signing_reference)
		self.assertEqual(doc.signatory_detail[1].signature_status, "Review In-Progress")
		self.assertTrue(
			get_decrypted_password("emSigner Signatory Detail", active.name, fieldname="callback_key")
		)

	def test_legacy_custom_position_needs_review_and_edits_revoke_old_link(self):
		row = self.doc.signatory_detail[0]
		frappe.db.set_value(
			"emSigner Signatory Detail",
			row.name,
			{"sign_position": "Customize", "customize_coordinates": "10,20,60,40", "coordinates_reviewed": 0},
		)
		frappe.db.commit()
		self.assertEqual(self.start().status_code, 400)
		request_sign.update_coordinates_value(
			"emSigner Signatory Detail", row.name, "12,24,60,40", sign_position="Customize"
		)
		frappe.db.commit()
		row = self.read_doc().signatory_detail[0]
		self.assertEqual(row.signature_status, "Not Initiated")
		self.assertTrue(row.coordinates_reviewed)
		self.assertFalse(row.reference_id)
		self.assertEqual(self.start().status_code, 400)

	def test_failure_response_releases_only_the_matching_attempt(self):
		import hashlib
		import hmac

		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		key = base64.b64decode(
			get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		)
		token = hmac.new(key, row.signing_reference.encode(), hashlib.sha256).hexdigest()
		bad = self.request(
			"GET", operation=lambda: emsigner_decrypt.signing_failed(row.signing_reference, "wrong")
		)
		self.assertEqual(bad.status_code, 400)
		self.assertEqual(self.read_doc().signatory_detail[0].signature_status, "Review In-Progress")
		response = self.request(
			"GET", operation=lambda: emsigner_decrypt.signing_failed(row.signing_reference, token)
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.read_doc().signatory_detail[0].signature_status, "Failure")
		self.assertEqual(self.start().status_code, 200)

	def test_sending_pending_invites_does_not_remove_an_active_callback_key(self):
		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		before = get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		with patch.object(request_sign, "send_email") as email:
			request_sign.send_email_request(TEST_DT, self.doc.name)
			frappe.db.commit()
		email.assert_not_called()
		self.assertEqual(
			get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key"), before
		)
		self.assertEqual(self.callback(self.read_doc().signatory_detail[0]).status_code, 303)

	def test_preview_warns_on_shared_presets_and_excludes_disjoint_pages(self):
		for row in self.doc.signatory_detail:
			frappe.db.set_value("emSigner Signatory Detail", row.name, "signature_status", "Not Initiated")
		frappe.db.commit()
		with patch.object(make_sign, "_get_document_pdf", return_value=self.source_pdf):
			result = make_sign.preview_before_signing(TEST_DT, self.doc.name)
		self.assertTrue(any("same preset position" in warning for warning in result["warnings"]))
		frappe.db.set_value(
			"emSigner Signatory Detail", self.doc.signatory_detail[1].name, "select_page", "EVEN"
		)
		frappe.db.commit()
		with patch.object(make_sign, "_get_document_pdf", return_value=self.source_pdf):
			result = make_sign.preview_before_signing(TEST_DT, self.doc.name)
		self.assertFalse(any("same preset position" in warning for warning in result["warnings"]))

	def test_failed_file_pointer_update_rolls_back_file_status_and_allows_retry(self):
		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		key = base64.b64decode(
			get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		)
		body = urlencode(
			{
				"Referencenumber": row.signing_reference,
				"Returnvalue": AES_ECB_Cipher(key).encrypt(self.source_pdf).decode(),
			}
		)
		with patch.object(
			emsigner_decrypt, "update_file_url", side_effect=OSError("synthetic write refusal")
		):
			self.assertEqual(self.request("POST", body=body).status_code, 503)
		doc = self.read_doc()
		self.assertEqual(doc.signatory_detail[0].signature_status, "Review In-Progress")
		self.assertFalse(doc.signed_document)
		self.assertEqual(
			frappe.db.count("File", {"attached_to_doctype": TEST_DT, "attached_to_name": self.doc.name}), 0
		)
		self.assertEqual(self.request("POST", body=body).status_code, 303)

	def test_owner_can_revoke_unused_link_for_review_but_not_active_or_completed(self):
		row = self.doc.signatory_detail[0]
		frappe.db.set_value(
			"emSigner Signatory Detail",
			row.name,
			{"sign_position": "Customize", "customize_coordinates": "10,20,60,40", "coordinates_reviewed": 0},
		)
		frappe.db.commit()
		request_sign.prepare_placement_review(TEST_DT, self.doc.name, row.name)
		frappe.db.commit()
		current = self.read_doc().signatory_detail[0]
		self.assertEqual(current.signature_status, "Not Initiated")
		self.assertFalse(current.reference_id)
		self.assertFalse(current.coordinates_reviewed)
		self.assertEqual(current.customize_coordinates, "10,20,60,40")
		for status in ("Review In-Progress", "Completed"):
			frappe.db.set_value(
				"emSigner Signatory Detail",
				row.name,
				{"signature_status": status, "last_tried": now_datetime()},
			)
			frappe.db.commit()
			with self.assertRaises(frappe.ValidationError):
				request_sign.prepare_placement_review(TEST_DT, self.doc.name, row.name)
			self.assertEqual(self.read_doc().signatory_detail[0].signature_status, status)
		with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError), self.assertRaises(
			frappe.PermissionError
		):
			request_sign.prepare_placement_review(TEST_DT, self.doc.name, row.name)

	def test_document_delete_clears_active_child_keys_through_the_trash_hook(self):
		self.assertEqual(self.start().status_code, 200)
		row = self.read_doc().signatory_detail[0]
		self.assertTrue(
			get_decrypted_password("emSigner Signatory Detail", row.name, fieldname="callback_key")
		)
		# Local disposable benches can load the app schema without installing hooks.
		# Exercise Frappe's real delete dispatcher with the shipped hook binding.
		import copy

		hooks = copy.deepcopy(frappe.get_doc_hooks())
		hooks.setdefault("*", {}).setdefault("on_trash", [])
		handler = "emsigner.emsigner.api.signing_state.clear_document_keys"
		if handler not in hooks["*"]["on_trash"]:
			hooks["*"]["on_trash"].append(handler)
		from emsigner.emsigner.api.signing_state import clear_document_keys

		original_get_attr = frappe.get_attr

		def resolve_hook(method):
			return clear_document_keys if method == handler else original_get_attr(method)

		with patch.object(frappe, "get_doc_hooks", return_value=hooks), patch.object(
			frappe, "get_attr", side_effect=resolve_hook
		):
			frappe.delete_doc(TEST_DT, self.doc.name, ignore_permissions=True, force=True)
		frappe.db.commit()
		self.assertIsNone(
			get_decrypted_password(
				"emSigner Signatory Detail", row.name, fieldname="callback_key", raise_exception=False
			)
		)
		self.assertFalse(frappe.db.exists(TEST_DT, self.doc.name))
