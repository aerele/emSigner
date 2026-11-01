"""Keep existing gateway behaviour and overlap old emailed links for seven days."""

import secrets
from datetime import timedelta

import frappe
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password, set_encrypted_password

from emsigner.emsigner.api.emsigner import DEMO_GATEWAY
from emsigner.emsigner.utils.py.create_custom_fields import make_custom_fields


def execute():
	settings = "emSigner Settings"
	# A newly added Single field has no stored value on an existing site.
	if not frappe.db.get_single_value(settings, "gateway_url"):
		frappe.db.set_single_value(settings, "gateway_url", DEMO_GATEWAY)
	if not get_decrypted_password(settings, settings, fieldname="signing_secret", raise_exception=False):
		set_encrypted_password(settings, settings, secrets.token_urlsafe(32), fieldname="signing_secret")
		frappe.db.set_single_value(settings, "signing_secret", "********")
	if not frappe.db.get_single_value(settings, "legacy_links_until"):
		frappe.db.set_single_value(settings, "legacy_links_until", now_datetime() + timedelta(days=7))
	for doctype in frappe.get_all("emSigner Doctype", filters={"parent": settings}, pluck="doctype_name"):
		make_custom_fields(doctype, "emSigner")
	frappe.db.add_index("emSigner Signatory Detail", ["signing_reference"])
	frappe.db.add_index("emSigner Signatory Detail", ["reference_id"])
