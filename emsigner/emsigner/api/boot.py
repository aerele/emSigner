import frappe


def get_emsigner_boot_info(bootinfo):
	doctypes = frappe.get_all(
		"emSigner Doctype", {"parent": "emSigner Settings"}, pluck="doctype_name"
	)
	bootinfo.emsigner_doctypes = doctypes
