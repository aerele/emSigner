import frappe


def delete_custom_fields(doctype, module=None):
	filters = {"dt": doctype}
	if module:
		filters["module"] = module
	field_list = frappe.get_all("Custom Field", filters=filters, pluck="name")
	for field in field_list:
		frappe.delete_doc("Custom Field", field)
