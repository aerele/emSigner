frappe.pages["redirected-to-emsign"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Redirected to emSigner portal",
		single_column: true,
	});
};
