import frappe
from frappe import _


def generate_failure_page(message):
	"""Redirect to failure page with message. Raises frappe.Redirect to halt execution."""
	frappe.redirect_to_message(_("Failure"), _(message))
	raise frappe.Redirect
