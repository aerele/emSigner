// Copyright (c) 2025, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.call({
	method: "frappe.client.get",
	args: {
		doctype: "emSigner Settings",
		name: "emSigner Settings",
	},
	callback: function (response) {
		let doctype_list = response.message["doctypes"];
		doctype_list.forEach((element) => {
			let doctype_name = element.doctype_name;
			frappe.ui.form.on(doctype_name, {
				refresh: function (frm) {
					frm.add_custom_button("Request Sign", function () {
						frappe.call({
							method: "emsigner.emsigner.api.request_sign.send_email_request",
							args: {
								docname: frm.doc.name,
								doctype: frm.doc.doctype,
							},
							callback: (response) => {
								frappe.msgprint("Signature requests has been sent successfully");
							},
						});
					});
					frm.add_custom_button("Fetch Sign info", function () {
						frappe.confirm(
							"This will clear the current Signatory Details. Are you sure you want to proceed?",
							function () {
								frappe.call({
									method: "emsigner.emsigner.api.make_sign.fetch_emsigner_authorized_signatory",
									args: {
										docname: frm.doc.name,
										doctype: frm.doc.doctype,
									},
									callback: (response) => {
										frappe.msgprint(
											"Default Signatory details fetched successfully"
										);
									},
								});
							}
						);
					});
				},
			});
			frappe.ui.form.on("emSigner Signatory Detail", {
				place_sign: function (frm, cdt, cdn) {
					var row = locals[cdt][cdn];
					frappe.msgprint({
						title: __("Set Coordinates"),
						message: `
						<p>Download the Signed/New PDF and follow the instruction in the video to find the 'Coordinates' and set it</p>
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
								frappe.call({
									method: "emsigner.emsigner.api.make_sign.download_document_pdf",
									args: {
										doctype: cur_frm.doc.doctype,
										docname: cur_frm.doc.name,
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
											link.download = `${cur_frm.doc.name}.pdf`;
											document.body.appendChild(link);
											link.click();
											document.body.removeChild(link);
										} else {
											frappe.msgprint(__("Failed to generate PDF"));
										}
									},
								});
							},
						},
					});

					// Add event listener for third button
					setTimeout(() => {
						document
							.getElementById("third-action-btn")
							.addEventListener("click", function () {
								window.open("https://coordinates-int.emsigner.com/");
							});
					}, 500);
					// if(row.sign_position == "Customize"){
					// 	frappe.call({
					// 		method: "emsigner.emsigner.api.request_sign.place_signature_page",
					// 		args: {
					// 			doctype: frm.doc.doctype,
					// 			child_doctype: row.doctype,
					// 			docname: frm.doc.name,
					// 			signatory_details: JSON.stringify(row),
					// 		},
					// 		callback: (response) => {
					// 			let newWindow = window.open("");
					// 			if (newWindow) {
					// 				newWindow.document.write(response.message);
					// 				newWindow.document.close();
					// 			} else {
					// 				console.error("Popup blocked. Enable popups for this site.");
					// 			}
					// 		},
					// 	});
					// }
					// else{
					// frappe.throw("Sign Position should be 'Customize' to place the signature")
					// }
				},
			});
		});
	},
});
