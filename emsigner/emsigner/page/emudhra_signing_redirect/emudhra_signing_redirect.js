frappe.pages["emudhra_signing_redirect"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "eMudhra Signing Redirect",
		single_column: true,
	});

	const ref_number = frappe.utils.get_url_arg("ref_number");

	if (!ref_number) {
		show_error(wrapper, __("Missing reference ID. Please close this tab and try again."));
		return;
	}

	frappe.call({
		method: "emsigner.emsigner.api.emsigner.get_signing_data",
		args: { ref_number: ref_number },
		callback: function (response) {
			if (response && response.message) {
				show_redirect_ui(wrapper, response.message);
			} else {
				show_error(wrapper, __("Signing data not found or has expired. Please try again."));
			}
		},
		error: function () {
			show_error(wrapper, __("Failed to fetch signing data. Please try again."));
		},
	});
};

function show_redirect_ui(wrapper, signingData) {
	const gateway_url = signingData.gateway_url
		|| "https://signergateway.emsigner.com/eMsecure/V3_0/Index";

	// Validate gateway URL points to a trusted emsigner domain
	try {
		const parsed = new URL(gateway_url);
		if (!parsed.hostname.endsWith(".emsigner.com")) {
			show_error(wrapper, __("Invalid gateway URL configured. Please contact your administrator."));
			return;
		}
	} catch (e) {
		show_error(wrapper, __("Invalid gateway URL configured. Please contact your administrator."));
		return;
	}

	// Build form safely using DOM API to avoid XSS
	const container = document.createElement("div");

	const form = document.createElement("form");
	form.id = "signDocForm";
	form.name = "signDocForm";
	form.method = "post";
	form.action = gateway_url;

	const input1 = document.createElement("input");
	input1.type = "hidden";
	input1.name = "Parameter1";
	input1.value = signingData.encrypted_session_key || "";
	form.appendChild(input1);

	const input2 = document.createElement("input");
	input2.type = "hidden";
	input2.name = "Parameter2";
	input2.value = signingData.encrypted_data || "";
	form.appendChild(input2);

	const input3 = document.createElement("input");
	input3.type = "hidden";
	input3.name = "Parameter3";
	input3.value = signingData.encrypted_hash || "";
	form.appendChild(input3);

	container.appendChild(form);

	const spinnerHtml = `
		<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 70vh; gap: 16px;">
			<div style="width: 48px; height: 48px; border: 3px solid var(--border-color); border-top-color: var(--primary); border-radius: 50%; animation: emsigner-spin 0.8s linear infinite;"></div>
			<h3 style="margin: 0; color: var(--heading-color); font-weight: 600;">Redirecting to eMudhra Portal</h3>
			<p style="margin: 0; color: var(--text-muted); font-size: 14px;">Please wait. Do not press Refresh or Back.</p>
		</div>
		<style>
			@keyframes emsigner-spin {
				to { transform: rotate(360deg); }
			}
		</style>
	`;

	$(wrapper).html(container);
	$(wrapper).append(spinnerHtml);

	setTimeout(() => {
		form.submit();
	}, 500);
}

function show_error(wrapper, message) {
	const $section = $(wrapper).find(".layout-main-section");
	const $container = $(`
		<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 50vh; gap: 12px;">
			<div style="font-size: 48px; color: var(--red-500);">&#10060;</div>
			<h4 style="margin: 0; color: var(--heading-color);">Error</h4>
			<p style="margin: 0; color: var(--text-muted); text-align: center; max-width: 400px;"></p>
		</div>
	`);
	// Set message as text to prevent XSS
	$container.find("p").text(message);
	$section.empty().append($container);
}
