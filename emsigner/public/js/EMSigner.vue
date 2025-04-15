<template>
	<div class="emSigner">
		<div class="content">Emsigner</div>
	</div>
</template>
<script>
export default {
	data() {
		return {};
	},

	watch: {
		async $route() {
			frappe.router.current_route = await frappe.router.parse();
			console.log("async $route");
			frappe.breadcrumbs.update();
		},
	},
};
</script>
