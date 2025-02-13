# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class emSignerLog(Document):
	pass


def clear_emsigner_logs_after_days_rq_job():
	frappe.enqueue(
		clear_emsigner_logs_after_days,
		queue="long",
		is_async=True,
		job_name="emSigner Log cleanup",
	)


def clear_emsigner_logs_after_days():
	no_of_days = frappe.db.get_value("emSigner Settings", "emSigner Settings", "clear_logs_after_days")
	delete_upto = (datetime.today() - timedelta(days=cint(no_of_days))).date()
	frappe.db.delete("emSigner Log", {"creation": ["<", f"{delete_upto} 23:59:59"]})
