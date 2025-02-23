import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def make_custom_fields():
	doctype_list = frappe.get_all("emSigner Doctype", {"parent": "emSigner Settings"}, pluck="doctype_name")
	for doctype in doctype_list:
		custom_fields = {
			doctype: [
				dict(
					fieldname="emsigner_tb",
					label="emSigner Details",
					fieldtype="Tab Break",
					insert_after=frappe.get_meta("Sales Invoice").fields[-1].fieldname,
					print_hide=1,
				),
				dict(
					fieldname="emsigner_sb_1",
					fieldtype="Section Break",
					insert_after="emsigner_tb",
					print_hide=1,
				),
				dict(
					fieldname="signed_document",
					label="Signed Document",
					fieldtype="Attach",
					insert_after="emsigner_sb_1",
					allow_on_submit=1,
				),
				dict(
					fieldname="emsigner_cb",
					fieldtype="Column Break",
					insert_after="signed_document",
				),
				dict(
					fieldname="requested_print_format",
					label="Requested Print Format",
					fieldtype="Data",
					insert_after="emsigner_cb",
					allow_on_submit=1,
				),
				dict(
					fieldname="requested_letter_head",
					label="Requested Letter Head",
					fieldtype="Data",
					insert_after="requested_print_format",
					allow_on_submit=1,
				),
				dict(
					fieldname="emsigner_sb_2",
					fieldtype="Section Break",
					insert_after="requested_letter_head",
					print_hide=1,
				),
				dict(
					fieldname="signatory_detail",
					label="Signatory Detail",
					fieldtype="Table",
					insert_after="emsigner_sb_2",
					options="emSigner Signatory Detail",
					allow_on_submit=1,
				),
			]
		}

		create_custom_fields(custom_fields)
