import frappe


def delete_custom_fields(doctype, module=None):
	field_list = frappe.get_all("Custom Field", {"dt": doctype, "module": module}, pluck="name")
	for field in field_list:
		frappe.delete_doc("Custom Field", field)
