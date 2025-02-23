import uuid
from datetime import datetime, timedelta

import frappe
import jwt
from frappe import _
from frappe.utils import get_url
from frappe.utils.data import quoted


def send_email_request(doctype, docname):
	doc = frappe.get_doc(doctype, docname)

	for row in doc.signatory_detail:
		if row.signature_status in ["Not Initiated", "Failure"]:
			row.reference_id = generate_reference_id()
			request_link = generate_request_link(
				doctype=doctype,
				docname=docname,
				recipient_email=row.signatory_email,
				reference_id=row.reference_id,
			)
			send_email(
				row.signatory_name, row.signatory_email, request_link, doc.modified_by, doctype, docname
			)
			row.signature_status = "Pending Review"
	doc.save()


def generate_reference_id():
	return uuid.uuid4().hex


def generate_request_link(doctype, docname, recipient_email, reference_id):
	token = jwt.encode(
		{"email": recipient_email, "exp": datetime.now() + timedelta(days=7)}, reference_id, algorithm="HS256"
	)

	base_url = get_url("/api/method/emsigner.emsigner.api.make_sign.make_sign")
	return (
		f"{base_url}?doctype={quoted(doctype)}&docname={quoted(docname)}&ref_id={reference_id}&token={token}"
	)


def send_email(signatory_name, recipient_email, request_link, modified_by, doctype, docname):
	frappe.sendmail(
		recipients=[recipient_email],
		subject=_("Request for Signature"),
		message=get_email_content(signatory_name, request_link, modified_by),
		reference_doctype=doctype,
		reference_name=docname,
	)


def get_email_content(signatory_name, link, author):
	author_name = frappe.utils.get_fullname(author)

	return f"""
	<html>
	<body>
		<p>Dear {signatory_name},</p>

		<p>I hope you're doing well.</p>

		<p>Please review and sign the document using the link below:</p>

		<p><a href="{link}" style="color: #007bff; text-decoration: none; font-weight: bold;">Sign Document</a></p>

		<p>If you have any questions, feel free to reach out.</p>

		<p>Best regards,</p>
		<p>{author_name}</p>
	</body>
	</html>
	"""
