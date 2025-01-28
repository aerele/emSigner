// import { createApp } from "vue";
// import { routes } from "./router";
// import { createWebHistory } from "vue-router";
// import EMSigner from "./EMSigner.vue";

// class EMSigner {

//     constructor(wrapper, pageName) {
//         this.pageName = pageName;
//         this.wrapperId = `#${wrapper.id}`;
//         this.setTitle();
//         // this.show();
//     }

//     setTitle() {
//         frappe.utils.set_title(__("EMSigner Account"));
//     }

//     createRouter() {
//         const history = createWebHistory("/app/emsigner-account");

//         history.listen(to => {
//             if (frappe.get_route_str().startsWith(this.pageName)) return;

//             frappe.route_flags.replace_route = true;
//             frappe.router.push_state(to);
//             this.router.listening = false;
//         });

//         return createRouter({
//             history: history,
//             routes: routes,
//         });
//     }

//     mountVueApp() {
//         this.router = this.createRouter();
//         this.app = createApp(EMSigner).use(this.router);
//         SetVueGlobals(this.app);
//         this.router.isReady().then(() => this.app.mount(this.wrapperId));
//     }

//     // show() {
//     //     this.mountVueApp();

//     //     $(frappe.pages[this.pageName]).on("show", () => {
//     //         this.router.listening = true;
//     //         this.setTitle();
//     //         this.router.replace(frappe.router.current_route.slice(1).join("/") || "/");
//     //     });
//     // }
// }

// frappe.provide("emsigner.pages")
// emsigner.pages.EMSigner = EMSigner;