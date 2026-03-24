import frappe


def get_context(context):
	ref = frappe.form_dict.get("ref")
	if not ref:
		context.doctype = ""
		context.docname = ""
		return

	signatory = frappe.db.get_value(
		"emSigner Signatory Detail",
		{"reference_id": ref},
		["parent", "parenttype"],
		as_dict=True,
	)
	if signatory:
		context.doctype = signatory.parenttype
		context.docname = signatory.parent
	else:
		context.doctype = ""
		context.docname = ""
