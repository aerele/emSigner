frappe.pages['emsigner-dashboard'].on_page_load = function(wrapper) {
	// var page = frappe.ui.make_app_page({
	// 	parent: wrapper,
	// 	title: 'EMSigner Dashboard',
	// 	single_column: true
	// });
	new Dashboard(wrapper)
}

var Dashboard = Class.extend({
	init: function (wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: 'EMSigner Dashboard',
			single_column: true
		});
		this.main();
	},

	main: function () {
        // this.setup_dashboard_widgets();
        // this.setup_dashboard_events();
		let me = this;
		
		let body = `
			<div id="content-container;>
				<img src="https://emudhra.com/hs-fs/hubfs/images/logo.webp?width=220&height=60&name=logo.webp" alt="LOGO" width="32" height="32">

			</div>`;

		$(frappe.render_template(body, this)).appendTo(this.page.main);
    },
})