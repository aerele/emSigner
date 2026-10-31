# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe.model.document import Document

from emsigner.emsigner.api.emsigner import DEMO_GATEWAY, validate_gateway_url
from emsigner.emsigner.utils.py.create_custom_fields import make_custom_fields

MODULE_NAME = "emSigner"


class emSignerSettings(Document):
	def validate(self):
		self.gateway_url = validate_gateway_url(self.gateway_url or DEMO_GATEWAY)
		if not self.signing_secret:
			self.signing_secret = secrets.token_urlsafe(32)
		from emsigner.emsigner.api.make_sign import _parse_coordinates

		old = self.get_doc_before_save()
		previous = {row.name: row.customize_coordinates for row in old.authorized_signatory} if old else {}
		for row in self.authorized_signatory:
			if row.customize_coordinates and previous.get(row.name) != row.customize_coordinates:
				if not _parse_coordinates(row.customize_coordinates):
					frappe.throw("Set finite left, top, width and height coordinates.")
				row.coordinates_reviewed = 1
		# Preset placement configuration must also enable its DocType.
		for row in self.print_format:
			if row.permitted_doctype not in {item.doctype_name for item in self.doctypes}:
				self.append("doctypes", {"doctype_name": row.permitted_doctype})

	def on_update(self):
		old_doc = self.get_doc_before_save()
		if not old_doc:
			# First save — create custom fields for all configured doctypes
			for dt in self.doctypes:
				make_custom_fields(dt.doctype_name, MODULE_NAME)
			return

		old_doctype_names = {d.doctype_name for d in old_doc.doctypes}
		new_doctype_names = {d.doctype_name for d in self.doctypes}
		added_doctypes = new_doctype_names - old_doctype_names
		# Disabling signing must retain existing signed PDFs and child history.
		# Custom fields can be removed only through an explicit data migration.
		for dt_name in added_doctypes:
			make_custom_fields(dt_name, MODULE_NAME)
