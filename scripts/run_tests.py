"""Run native transaction tests on a disposable, explicitly named test site."""

import os
import sys
import unittest
from pathlib import Path

import frappe

site = sys.argv[1]
if not site.startswith("test_"):
	raise SystemExit("Use a disposable site whose name starts with test_.")
sites_path = Path("sites").resolve()
os.chdir(sites_path)
frappe.init(site=site, sites_path=str(sites_path))
frappe.connect()
frappe.set_user("Administrator")
frappe.flags.in_test = True
frappe.in_test = True
try:
	if os.environ.get("EMSIGNER_TEST_ISOLATION") == "REPEATABLE READ":
		frappe.db.commit()
		frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
	suite = unittest.defaultTestLoader.loadTestsFromNames(
		[
			"emsigner.tests.test_signing_security",
			"emsigner.tests.test_signing_flow",
		]
	)
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	raise SystemExit(not result.wasSuccessful())
finally:
	frappe.db.rollback()
	frappe.destroy()
