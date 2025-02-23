frappe.pages["emudhra_signing_redirect"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "eMudhra Signing Redirect",
		single_column: true,
	});
	frappe.call({
		method: "emsigner.emsigner.api.emsigner.get_signing_data",
		callback: function (response) {
			console.log(response);
			if (response && response.message) {
				const signingData = response.message;
				retrieveSigningData(wrapper, signingData);
			} else {
				page.set_body("<h3>Error</h3><p>Signing data not found. Please try again.</p>");
			}
		},
		error: function () {
			page.set_body("<h3>Error</h3><p>Failed to fetch signing data. Please try again.</p>");
		},
	});
};

function retrieveSigningData(wrapper, signingData) {
	if (signingData) {
		var formHtml = `
            <form id="signDocForm" name="signDocForm" method="post" action="https://demosignergateway.emsigner.com/eMsecure/V3_0/Index">
                <input type="hidden" name="Parameter1" value="${signingData.encrypted_session_key}">
                <input type="hidden" name="Parameter2" value="${signingData.encrypted_data}">
                <input type="hidden" name="Parameter3" value="${signingData.encrypted_hash}">
            </form>
            <table align="center">
                <tbody>
                    <tr><td><strong>You are being redirected to the eMudhra portal</strong></td></tr>
                    <tr><td><font color="blue">Please wait ...</font></td></tr>
                    <tr><td>(Please do not press 'Refresh' or 'Back' button)</td></tr>
                </tbody>
            </table>
        `;
		$(wrapper).html(formHtml);
	} else {
		$(wrapper).html("<p>Error: Signing data not found.</p>");
	}
}
