import base64
import json
import uuid
from datetime import datetime, timedelta

import frappe
import jwt
from frappe import _
from frappe.utils import get_url
from frappe.utils.data import quoted

from emsigner.emsigner.api.make_sign import get_document_content


@frappe.whitelist()
def send_email_request(doctype, docname):
	doc = frappe.get_doc(doctype, docname)

	for row in doc.signatory_detail:
		if row.signature_status in ["Not Initiated", "Failure"]:
			row.reference_id = generate_reference_id()
			request_link = generate_request_link(
				doctype=doctype,
				docname=docname,
				recipient_email=row.signatory_email,
				reference_id=row.reference_id,
			)
			send_email(
				row.signatory_name, row.signatory_email, request_link, doc.modified_by, doctype, docname
			)
			row.signature_status = "Pending Review"
	doc.save()


def generate_reference_id():
	return uuid.uuid4().hex


def generate_request_link(doctype, docname, recipient_email, reference_id):
	token = jwt.encode(
		{"email": recipient_email, "exp": datetime.now() + timedelta(days=7)}, reference_id, algorithm="HS256"
	)

	base_url = get_url("/api/method/emsigner.emsigner.api.make_sign.make_sign")
	return (
		f"{base_url}?doctype={quoted(doctype)}&docname={quoted(docname)}&ref_id={reference_id}&token={token}"
	)


def send_email(signatory_name, recipient_email, request_link, modified_by, doctype, docname):
	frappe.sendmail(
		recipients=[recipient_email],
		subject=_("Request for Signature"),
		message=get_email_content(signatory_name, request_link, modified_by),
		reference_doctype=doctype,
		reference_name=docname,
	)


def get_email_content(signatory_name, link, author):
	author_name = frappe.utils.get_fullname(author)

	return f"""
	<html>
	<body>
		<p>Dear {signatory_name},</p>

		<p>I hope you're doing well.</p>

		<p>Please review and sign the document using the link below:</p>

		<p><a href="{link}" style="color: #007bff; text-decoration: none; font-weight: bold;">Sign Document</a></p>

		<p>If you have any questions, feel free to reach out.</p>

		<p>Best regards,</p>
		<p>{author_name}</p>
	</body>
	</html>
	"""


@frappe.whitelist()
def place_signature_page(doctype, child_doctype, docname, signatory_details):
	signatory_details = json.loads(signatory_details)
	file = get_document_content(doctype, docname, signatory_details)
	pdf_file = base64.b64encode(file).decode("utf-8")

	signatories = frappe.get_all(
		child_doctype, filters={"parent": docname}, fields=["signatory_name", "customize_coordinates"]
	)

	current_signatory = signatory_details.get("signatory_name")
	other_signatures_html = ""

	for signatory in signatories:
		if signatory["signatory_name"] != current_signatory and signatory["customize_coordinates"]:
			try:
				coords = signatory["customize_coordinates"].split(",")
				if len(coords) == 4:
					x, y, width, height = (float(coord) for coord in coords)
					other_signatures_html += f"""
						<div class="signature-static"
							 data-x="{x}"
							 data-y="{y}"
							 data-width="{width}"
							 data-height="{height}">
							{signatory['signatory_name']}
						</div>
					"""
			except (ValueError, IndexError):
				frappe.log_error(
					f"Invalid coordinates for {signatory['signatory_name']}: {signatory['customize_coordinates']}"
				)

	html = f"""
	<!DOCTYPE html>
	<html lang="en">
	<head>
		<meta charset="UTF-8">
		<meta name="viewport" content="width=device-width, initial-scale=1.0">
		<title>Signature Position Selector</title>
		<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.min.js"></script>
		<style>
			body {{
				font-family: Arial, sans-serif;
				text-align: center;
			}}
			#signature-box {{
				width: 600px;
				height: 800px;
				border: 2px dashed #000;
				position: relative;
				margin: 20px auto;
				background-color: #f0f0f0;
				overflow: hidden;
			}}
			.draggable {{
				width: auto;
				padding: 15px 30px;
				background-color: lightblue;
				position: absolute;
				cursor: grab;
				border: 1px solid #000;
				border-radius: 5px;
				z-index: 10;
				font-size: 24px;
			}}
			.signature-static {{
				width: auto;
				padding: 15px 30px;
				background-color: #e0e0e0;
				position: absolute;
				border: 1px solid #666;
				border-radius: 5px;
				opacity: 0.7;
				pointer-events: none;
				z-index: 5;
				font-size: 24px;
			}}
			#pdf-canvas {{
				position: absolute;
				top: 0;
				left: 0;
				width: 100%;
				height: 100%;
				z-index: 1;
			}}
			#submit-coordinates {{
				margin-top: 20px;
				padding: 10px 20px;
				background-color: green;
				color: white;
				border: none;
				cursor: pointer;
				font-size: 16px;
			}}
		</style>
	</head>
	<body>
		<h2>Drag and Drop Your Name to Mark Signature Position</h2>
		<div id="signature-box">
			<canvas id="pdf-canvas"></canvas>
			{other_signatures_html}
			<div id="draggable" class="draggable">{current_signatory or "Your Name"}</div>
		</div>
		<p id="coords">Coordinates: (0, 0)</p>
		<button id="submit-coordinates">Submit Coordinates</button>

		<script>
			const pdfBase64 = "{pdf_file}";
			const pdfCanvas = document.getElementById("pdf-canvas");
			const signatureBox = document.getElementById("signature-box");
			const draggable = document.getElementById("draggable");
			const coordsDisplay = document.getElementById("coords");
			const SCALE_FACTOR = 1.5;
			let offsetX, offsetY, isDragging = false;
			let pdfHeight = 0, pdfWidth = 0;
			let signatureCoordinates = {{ x: 0, y: 0, width: 0, height: 0 }};

			async function renderPDF(base64) {{
				const loadingTask = pdfjsLib.getDocument({{ data: atob(base64) }});
				const pdf = await loadingTask.promise;
				const page = await pdf.getPage(1);
				const viewport = page.getViewport({{ scale: SCALE_FACTOR }});
				pdfCanvas.width = viewport.width;
				pdfCanvas.height = viewport.height;
				signatureBox.style.width = `${{viewport.width}}px`;
				signatureBox.style.height = `${{viewport.height}}px`;
				pdfWidth = viewport.width;
				pdfHeight = viewport.height;
				const context = pdfCanvas.getContext("2d");
				await page.render({{ canvasContext: context, viewport }}).promise;
				positionStaticSignatures();
			}}

			function positionStaticSignatures() {{
				document.querySelectorAll('.signature-static').forEach(sig => {{
					let x = parseFloat(sig.dataset.x) * SCALE_FACTOR;
					let y = pdfHeight - (parseFloat(sig.dataset.y) * SCALE_FACTOR);
					sig.style.left = `${{x}}px`;
					sig.style.top = `${{y}}px`;
				}});
			}}

			renderPDF(pdfBase64);

			draggable.addEventListener("mousedown", (event) => {{
				isDragging = true;
				offsetX = event.clientX - draggable.getBoundingClientRect().left;
				offsetY = event.clientY - draggable.getBoundingClientRect().top;
			}});

			document.addEventListener("mousemove", (event) => {{
				if (!isDragging) return;
				let x = event.clientX - signatureBox.getBoundingClientRect().left - offsetX;
				let y = event.clientY - signatureBox.getBoundingClientRect().top - offsetY;
				x = Math.max(0, Math.min(x, signatureBox.clientWidth - draggable.clientWidth));
				y = Math.max(0, Math.min(y, signatureBox.clientHeight - draggable.clientHeight));
				draggable.style.left = `${{x}}px`;
				draggable.style.top = `${{y}}px`;
				signatureCoordinates = {{
					x: x / SCALE_FACTOR,
					y: (pdfHeight - y) / SCALE_FACTOR,
					width: (x + draggable.clientWidth) / SCALE_FACTOR,
					height: (y + draggable.clientHeight) / SCALE_FACTOR
				}};
				coordsDisplay.innerText = `Coordinates: (${{signatureCoordinates.x.toFixed(2)}}, ${{signatureCoordinates.y.toFixed(2)}}, ${{signatureCoordinates.width.toFixed(2)}}, ${{signatureCoordinates.height.toFixed(2)}})`;
			}});

			document.addEventListener("mouseup", () => {{
				isDragging = false;
			}});

			document.getElementById("submit-coordinates").addEventListener("click", function () {{
				fetch(`/api/method/emsigner.emsigner.api.request_sign.update_coordinates_value?doctype={doctype}&child_doctype={child_doctype}&docname={docname}&coordinates=${{signatureCoordinates.x.toFixed(2)}},${{signatureCoordinates.y.toFixed(2)}},${{signatureCoordinates.width.toFixed(2)}},${{signatureCoordinates.height.toFixed(2)}}&signatory_name=${{encodeURIComponent("{current_signatory}")}}`, {{ method: "GET" }})
				.then(response => response.json())
				.then(data => {{ alert(data.message ? "Coordinates updated successfully!" : "Failed to update coordinates."); }})
				.catch(() => alert("An error occurred while updating coordinates."));
			}});
		</script>
	</body>
	</html>
	"""
	return html


@frappe.whitelist(allow_guest=True)
def update_coordinates_value(doctype, child_doctype, docname, coordinates, signatory_name):
	try:
		coords = coordinates.split(",")
		if len(coords) != 4:
			frappe.throw(_("Invalid coordinate format. Expected 4 values: x,y,width,height"))

		x, y, width, height = (float(value.strip()) for value in coords)
		coordinates_data = {
			"x": x,
			"y": y,
			"width": width,
			"height": height,
			"format": "pdf_points",
			"timestamp": frappe.utils.now(),
		}
		coordinates_str = f"{x},{y},{width},{height}"
		query = f"""
			UPDATE `tab{child_doctype}`
			SET customize_coordinates = %s
			WHERE parent = %s
			AND signatory_name = %s
		"""
		frappe.db.sql(query, (coordinates_str, docname, signatory_name))
		frappe.db.commit()

		return {
			"message": "Coordinates updated successfully",
			"coordinates": coordinates_str,
			"debug": coordinates_data,
		}
	except Exception as e:
		frappe.log_error(
			"Coordinate Update Error",
			f"Error: {str(e)}, Coordinates: {coordinates}, Signatory: {signatory_name}",
		)
		frappe.throw(_("Failed to update coordinates: {0}").format(str(e)))
