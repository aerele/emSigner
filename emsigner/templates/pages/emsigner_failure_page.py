import frappe


def get_context(context):
	context.no_cache = 1
	context.doctype = context.docname = ""
	if frappe.session.user == "Guest":
		return
	ref = frappe.form_dict.get("ref")
	if not ref:
		return
	signatory = frappe.db.get_value(
		"emSigner Signatory Detail", {"reference_id": ref}, ["parent", "parenttype"], as_dict=True
	)
	if signatory and frappe.has_permission(signatory.parenttype, "read", signatory.parent):
		context.doctype, context.docname = signatory.parenttype, signatory.parent
