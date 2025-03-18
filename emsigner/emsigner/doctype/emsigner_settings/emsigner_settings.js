// Copyright (c) 2025, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("emSigner Settings", {});

frappe.ui.form.on("emSigner Authorized Signatory", {
	place_sign: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.sign_position == "Customize") {
			frappe.msgprint({
				title: __("Set Coordinates"),
				message: `
				<p>Download the Signed/New PDF and follow the instruction in the video to find the 'Coordinates' and set it.</p>
				<iframe width="100%" height="315"
					src="https://www.youtube.com/embed/34xhjJEnaRA?autoplay=1&mute=1"
					frameborder="0" allowfullscreen>
				</iframe>
				<br><br>
				<button class="btn btn-primary" id="third-action-btn">Open Site</button>
				`,
				primary_action: {
					label: "Set the Coordinates",
					action() {
						frappe.hide_msgprint();
						frappe.prompt("Coordinates", ({ value }) => {
							frappe.model.set_value(
								row.doctype,
								row.name,
								"customize_coordinates",
								value
							);
							frm.save();
						});
					},
				},
				secondary_action: {
					label: "Download PDF",
					action() {
						frappe.hide_msgprint();
						frappe.prompt(
							[
								{
									label: "Sales Invoice",
									fieldname: "sales_invoice",
									fieldtype: "Link",
									options: "Sales Invoice",
									reqd: 1,
								},
							],
							({ sales_invoice }) => {
								frappe.call({
									method: "emsigner.emsigner.api.make_sign.download_document_pdf",
									args: {
										doctype: row.permitted_doctype,
										docname: sales_invoice,
										signatory_details: row,
									},
									callback(r) {
										if (r.message) {
											// Decode Base64 string to binary
											let byteCharacters = atob(r.message);
											let byteNumbers = new Array(byteCharacters.length);
											for (let i = 0; i < byteCharacters.length; i++) {
												byteNumbers[i] = byteCharacters.charCodeAt(i);
											}
											let byteArray = new Uint8Array(byteNumbers);
											let blob = new Blob([byteArray], {
												type: "application/pdf",
											});

											// Create a download link
											let link = document.createElement("a");
											link.href = URL.createObjectURL(blob);
											link.download = `${sales_invoice}.pdf`;
											document.body.appendChild(link);
											link.click();
											document.body.removeChild(link);
										} else {
											frappe.msgprint(__("Failed to generate PDF"));
										}
									},
								});
							}
						);
					},
				},
			});
			setTimeout(() => {
				document.getElementById("third-action-btn").addEventListener("click", function () {
					window.open("https://coordinates-int.emsigner.com/");
				});
			}, 500);
		} else {
			frappe.throw("The sign position should be 'Customize' to place sign");
		}
	},
});
