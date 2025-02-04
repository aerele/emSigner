// Copyright (c) 2025, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.call({
    method: 'frappe.client.get',
    args: {
        doctype: 'Emudhra emSigner Gateway',
        name: 'Emudhra emSigner Gateway'
    },
    callback: function(response) {
        let doctype_list = response.message["emudhra_emsign_doctypes"]
		doctype_list.forEach(element => {
			let doctype_name = element.doctype_name;
			frappe.ui.form.on(doctype_name, {
				refresh: function(frm) {
					frm.add_custom_button('Sign', function() {
						let d = new frappe.ui.Dialog({
							title: 'Enter details',
							fields: [
								{
									label: 'Name',
									fieldname: 'name',
									fieldtype: 'Data',
									default: frappe.session.user_fullname
								},
								{
									label: 'Print Format',
									fieldname: 'print_format',
									fieldtype: 'Link',
									options: 'Print Format',
									default: 'Standard'
								},
								{
									label: 'Letter Head',
									fieldname: 'letter_head',
									fieldtype: 'Link',
									options: 'Letter Head'
								}
							],
							size: 'small', 
							primary_action_label: 'Submit',
							primary_action(values) {
								console.log(values, "values")
								frappe.call({
									method: "emsigner.emsigner.doctype.emudhra_emsigner_gateway.emudhra_emsigner_gateway.get_emsigner_parameters",
									args: {
										"doctype_name": doctype_name,
										"document_name": frm.doc.name,
										"print_format": values.print_format,
										"letter_head": values.letter_head,
										"name": values.name
									},
									callback: (response) => {
                                        const iframeContent = response.message;
                                        const iframeBlob = new Blob([iframeContent], { type: 'text/html' });
                                        const iframeURL = URL.createObjectURL(iframeBlob);
                                        const htmlWrapper = `
                                            <!DOCTYPE html>
                                            <html lang="en">
                                            <head>
                                                <meta charset="UTF-8">
                                                <title>Emudhra emsign Portal</title>
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
                                        const wrapperBlob = new Blob([htmlWrapper], { type: 'text/html' });
                                        const wrapperURL = URL.createObjectURL(wrapperBlob);
                                        const features = "width=800,height=600,noopener,noreferrer";
                                        const newWindow = window.open(wrapperURL, "_blank", features);
									}
								});
								d.hide();
							}
						});
						
						d.show();
					});
				},
			})
			
		});
    }
});