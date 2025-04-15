from urllib.parse import quote

import frappe
import requests
from frappe import _
from frappe.utils.response import Response
from frappe.website.page_renderers.redirect_page import RedirectPage
from frappe.website.serve import get_response
from werkzeug.utils import redirect


@frappe.whitelist(allow_guest=True)
def generate_failure_page(message):
	frappe.redirect_to_message(
		_("Failure"),
		_(message),
	)


@frappe.whitelist()
def upload_file(file_data):
	try:
		# Prepare headers
		headers = {
			"accept": "*/*",
			"accept-language": "en-GB,en;q=0.9",
			"origin": "https://coordinates-int.emsigner.com",
			"referer": "https://coordinates-int.emsigner.com/",
			"sec-ch-ua": '"Not(A:Brand";v="99", "Brave";v="133", "Chromium";v="133"',
			"sec-ch-ua-mobile": "?0",
			"sec-ch-ua-platform": '"Linux"',
			"sec-fetch-dest": "empty",
			"sec-fetch-mode": "cors",
			"sec-fetch-site": "same-origin",
			"sec-gpc": "1",
			"user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
			"x-requested-with": "XMLHttpRequest",
		}

		# Convert base64 to file-like object if needed, or use raw data
		# Here we'll send it as a file
		import base64
		from io import BytesIO

		# Assuming raw base64 data
		file_content = base64.b64decode(file_data)
		files = {"Supportingattachments": ("document.pdf", BytesIO(file_content), "application/pdf")}

		# Make the request
		response = requests.post(
			"https://coordinates-int.emsigner.com/fileupload.ashx", headers=headers, files=files
		)

		response.raise_for_status()  # Raise exception for bad status codes
		return response.text

	except Exception as e:
		frappe.log_error(f"File upload failed: {str(e)}", "upload_file")
		frappe.throw(f"Upload failed: {str(e)}")
