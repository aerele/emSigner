# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from emsigner.emsigner.utils.py.create_custom_fields import make_custom_fields
from emsigner.emsigner.utils.py.delete_custom_fields import delete_custom_fields


class emSignerSettings(Document):
	def on_update(self):
		old_doc = self.get_doc_before_save()
		old_doctype_names = {d.doctype_name for d in old_doc.doctypes}
		new_doctype_names = {d.doctype_name for d in self.doctypes}
		removed_doctypes = old_doctype_names - new_doctype_names
		added_doctypes = new_doctype_names - old_doctype_names
		for dict in removed_doctypes:
			delete_custom_fields(dict, "emSigner")
		for dict in added_doctypes:
			make_custom_fields(dict, "emsigner")
