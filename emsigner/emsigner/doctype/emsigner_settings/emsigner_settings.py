# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from emsigner.emsigner.utils.py.create_custom_fields import make_custom_fields
from emsigner.emsigner.utils.py.delete_custom_fields import delete_custom_fields

MODULE_NAME = "emsigner"


class emSignerSettings(Document):
	def on_update(self):
		old_doc = self.get_doc_before_save()
		if not old_doc:
			# First save — create custom fields for all configured doctypes
			for dt in self.doctypes:
				make_custom_fields(dt.doctype_name, MODULE_NAME)
			return

		old_doctype_names = {d.doctype_name for d in old_doc.doctypes}
		new_doctype_names = {d.doctype_name for d in self.doctypes}
		removed_doctypes = old_doctype_names - new_doctype_names
		added_doctypes = new_doctype_names - old_doctype_names
		for dt_name in removed_doctypes:
			delete_custom_fields(dt_name, MODULE_NAME)
		for dt_name in added_doctypes:
			make_custom_fields(dt_name, MODULE_NAME)
