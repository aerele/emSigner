import frappe
from frappe import _
from markupsafe import escape
from werkzeug.wrappers import Response


class SigningFlowError(frappe.ValidationError):
	pass


def generate_failure_page(message):
	"""Stop a signing flow; browser entry points render this typed failure."""
	frappe.throw(message, exc=SigningFlowError)


def failure_response(message, status=400):
	body = f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
	<title>{escape(_("Signing could not continue"))}</title><style>
	:root{{color-scheme:light dark}}body{{font:1rem/1.6 system-ui;margin:0;padding:2rem;overflow-wrap:anywhere}}
	main{{max-width:38rem;margin:10vh auto}}h1{{font-size:1.6rem}}</style></head>
	<body><main><h1>{escape(_("Signing could not continue"))}</h1><p>{escape(message)}</p>
	<p>{escape(_("You can close this tab. Ask the document owner for help or a new link."))}</p></main></body></html>"""
	return Response(
		body,
		status=status,
		content_type="text/html; charset=utf-8",
		headers={
			"Cache-Control": "no-store",
			"Referrer-Policy": "no-referrer",
			"X-Content-Type-Options": "nosniff",
			"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
		},
	)
