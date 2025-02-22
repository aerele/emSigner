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
					frm.add_custom_button("Sign", function () {
						let d = new frappe.ui.Dialog({
							title: "Enter details",
							fields: [
								{
									label: "Name",
									fieldname: "name",
									fieldtype: "Data",
									default: frappe.session.user_fullname,
								},
								{
									label: "Print Format",
									fieldname: "print_format",
									fieldtype: "Link",
									options: "Print Format",
									default: "Standard",
								},
								{
									label: "Letter Head",
									fieldname: "letter_head",
									fieldtype: "Link",
									options: "Letter Head",
								},
								{
									label: "Select Page",
									fieldname: "select_page",
									fieldtype: "Select",
									options: "\nALL\nFIRST\nEVEN\nLAST\nODD\nSPECIFY\nPAGE LEVEL",
									default: "ALL",
									reqd: 1,
								},
								{
									label: "Page Number",
									fieldname: "page_number",
									fieldtype: "Data",
									depends_on: 'eval:doc.select_page == "SPECIFY"',
								},
								{
									label: "Page Level Coordinates",
									fieldname: "page_level_coordinates",
									fieldtype: "Data",
									depends_on: 'eval:doc.select_page == "PAGE LEVEL"',
								},
								{
									label: "Signature Position",
									fieldname: "signature_position",
									fieldtype: "Select",
									options:
										"Top-Left\nTop-Center\nTop-Right\nMiddle-Left\nMiddle-Center\nMiddle-Right\nBottom-Left\nBottom-Center\nBottom-Right\nCustomize",
									default: "Bottom-Right",
									reqd: 1,
								},
								{
									label: "Custom Co-ordinates",
									fieldname: "customize_coordinates",
									fieldtype: "Data",
									depends_on: 'eval:doc.signature_position == "Customize"',
								},
								{
									label: "Reason",
									fieldname: "reason",
									fieldtype: "Small Text",
								},
							],
							size: "small",
							primary_action_label: "Submit",
							primary_action(values) {
								frappe.call({
									method: "emsigner.emsigner.api.emsigner.get_emsigner_parameters",
									args: {
										doctype_name: doctype_name,
										document_name: frm.doc.name,
										name: values.name,
										print_format: values.print_format,
										letter_head: values.letter_head,
										select_page: values.select_page,
										page_number: values.page_number,
										page_level_coordinates: values.page_level_coordinates,
										signature_position: values.signature_position,
										customize_coordinates: values.customize_coordinates,
										reason: values.reason,
									},
									callback: (response) => {
										const iframeContent = response.message;
										const iframeBlob = new Blob([iframeContent], {
											type: "text/html",
										});
										const iframeURL = URL.createObjectURL(iframeBlob);
										const htmlWrapper = `
											<!DOCTYPE html>
											<html lang="en">
											<head>
												<meta charset="UTF-8">
												<title>emSign Portal</title>
												<style>
													body, html {
														margin: 0;
														padding: 0;
														height: 100%;
														overflow: hidden;
													}
													iframe {
														border: none;
														width: 100%;
														height: 100%;
													}
												</style>
											</head>
											<body>
												<iframe id="contentIframe" src="${iframeURL}" sandbox="allow-scripts allow-same-origin allow-forms allow-popups"></iframe>
											</body>
											</html>
										`;
										const wrapperBlob = new Blob([htmlWrapper], {
											type: "text/html",
										});
										const wrapperURL = URL.createObjectURL(wrapperBlob);
										const features =
											"width=800,height=600,noopener,noreferrer";
										const newWindow = window.open(
											wrapperURL,
											"_blank",
											features
										);
									},
								});
								d.hide();
							},
						});
						d.show();
					});
				},
			});
		});
	},
});
