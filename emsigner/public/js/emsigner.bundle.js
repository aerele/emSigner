// Copyright (c) 2025, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

(function () {
	// Track which doctypes/child tables already have handlers registered
	const registered_doctypes = new Set();
	let signatory_handler_registered = false;

	// Read enabled doctypes from boot info (no API call needed)
	frappe.after_ajax(() => {
		const doctypes = (frappe.boot.emsigner_doctypes || []);
		doctypes.forEach((doctype_name) => {
			setup_emsigner_form(doctype_name);
		});
	});

	function setup_emsigner_form(doctype_name) {
		if (registered_doctypes.has(doctype_name)) return;
		registered_doctypes.add(doctype_name);

		frappe.ui.form.on(doctype_name, {
			refresh(frm) {
				add_emsigner_buttons(frm);
				apply_status_indicators(frm);
			},
		});

		// Only register child table handlers once
		if (!signatory_handler_registered) {
			signatory_handler_registered = true;
			frappe.ui.form.on("emSigner Signatory Detail", {
				form_render(frm, cdt, cdn) {
					apply_status_indicators(frm);
				},
				place_sign(frm, cdt, cdn) {
					const row = locals[cdt][cdn];
					open_signature_placement_dialog(frm, row);
				},
			});
		}
	}

	function add_emsigner_buttons(frm) {
		if (frm.is_new()) return;

		const signatories = frm.doc.signatory_detail || [];
		const has_signatories = signatories.length > 0;
		const completed = signatories.filter((s) => s.signature_status === "Completed");
		const pending = signatories.filter((s) => s.signature_status !== "Completed");
		const any_sent = signatories.some((s) => s.signature_status !== "Not Initiated");

		// Show signing progress banner
		if (has_signatories) {
			show_signing_banner(frm, signatories, completed, pending);
		}

		frm.add_custom_button(
			__("Request Sign"),
			() => {
				validate_and_send_sign_request(frm);
			},
			__("emSigner")
		);

		if (has_signatories && any_sent) {
			frm.add_custom_button(
				__("Signing Status"),
				() => {
					show_signing_status_dialog(frm);
				},
				__("emSigner")
			);
		}

		frm.add_custom_button(
			__("Fetch Signatory Info"),
			() => {
				frappe.confirm(
					__("This will clear the current Signatory Details. Are you sure?"),
					() => {
						frappe.call({
							method: "emsigner.emsigner.api.make_sign.fetch_emsigner_authorized_signatory",
							args: { docname: frm.doc.name, doctype: frm.doc.doctype },
							freeze: true,
							freeze_message: __("Fetching signatory details..."),
							callback() {
								frappe.show_alert(
									{ message: __("Signatory details fetched successfully"), indicator: "green" },
									5
								);
								frm.reload_doc();
							},
						});
					}
				);
			},
			__("emSigner")
		);
	}

	function show_signing_banner(frm, signatories, completed, pending) {
		// Remove any previous emsigner banner
		frm.$wrapper.find(".emsigner-signing-banner").remove();

		let msg = "";
		let color = "";

		if (completed.length === signatories.length) {
			msg = __("All {0} signatory(ies) have signed. Submit this document to confirm.", [signatories.length]);
			color = "green";
		} else if (completed.length > 0) {
			msg = __("{0} of {1} signed. Waiting for: {2}", [
				completed.length,
				signatories.length,
				pending.map((s) => s.signatory_name).join(", "),
			]);
			color = "orange";
		} else if (signatories.some((s) => s.signature_status === "Pending Review" || s.signature_status === "Review In-Progress")) {
			msg = __("Signing in progress. {0} signatory(ies) pending.", [pending.length]);
			color = "blue";
		}

		if (msg) {
			const $banner = $(`<div class="emsigner-signing-banner" style="
				padding: 10px 15px; margin-bottom: 10px; border-radius: 6px; font-size: 13px;
				background: var(--${color}-50, var(--subtle-fg));
				border: 1px solid var(--${color}-200, var(--border-color));
				color: var(--${color}-600, var(--text-color));
			">${msg}</div>`);
			frm.layout.wrapper.find(".form-message").after($banner);
		}
	}

	function show_signing_status_dialog(frm) {
		const signatories = frm.doc.signatory_detail || [];

		const STATUS_ICONS = {
			"Not Initiated": { icon: "&#9711;", color: "var(--gray-500)" },
			"Pending Review": { icon: "&#9993;", color: "var(--orange-500)" },
			"Review In-Progress": { icon: "&#9998;", color: "var(--blue-500)" },
			Completed: { icon: "&#10004;", color: "var(--green-500)" },
			Rejected: { icon: "&#10006;", color: "var(--red-500)" },
			Failure: { icon: "&#10006;", color: "var(--red-500)" },
		};

		const rows_html = signatories.map((s) => {
			const status = s.signature_status || "Not Initiated";
			const si = STATUS_ICONS[status] || STATUS_ICONS["Not Initiated"];
			const name = frappe.utils.escape_html(s.signatory_name);
			const email = frappe.utils.escape_html(s.signatory_email);
			const can_resend = status === "Pending Review" || status === "Failure" || status === "Not Initiated";

			return `<div class="sig-status-row" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border-color);">
				<span style="font-size: 20px; color: ${si.color}; width: 28px; text-align: center;">${si.icon}</span>
				<div style="flex: 1; min-width: 0;">
					<div style="font-weight: 600; font-size: 14px;">${name}</div>
					<div style="font-size: 12px; color: var(--text-muted);">${email}</div>
				</div>
				<span class="indicator-pill ${STATUS_COLORS[status] || "grey"}" style="font-size: 12px;">${frappe.utils.escape_html(status)}</span>
				${can_resend ? `<button class="btn btn-xs btn-default resend-btn" data-email="${email}" data-name="${frappe.utils.escape_html(s.name)}">${__("Resend")}</button>` : ""}
			</div>`;
		}).join("");

		const completed_count = signatories.filter((s) => s.signature_status === "Completed").length;
		const total = signatories.length;
		const progress_pct = total ? Math.round((completed_count / total) * 100) : 0;

		const dialog = new frappe.ui.Dialog({
			title: __("Signing Status — {0}", [frm.doc.name]),
			size: "large",
		});

		dialog.$body.html(`
			<div style="padding: 0;">
				<div style="padding: 16px; background: var(--subtle-fg); border-bottom: 1px solid var(--border-color);">
					<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
						<span style="font-size: 13px; font-weight: 600;">${__("Progress")}</span>
						<span style="font-size: 13px; color: var(--text-muted);">${completed_count} / ${total}</span>
					</div>
					<div style="height: 8px; background: var(--border-color); border-radius: 4px; overflow: hidden;">
						<div style="height: 100%; width: ${progress_pct}%; background: var(--green-500); border-radius: 4px; transition: width 0.3s;"></div>
					</div>
				</div>
				<div class="sig-status-list">
					${rows_html}
				</div>
				${completed_count === total ? `
				<div style="padding: 16px; text-align: center; background: var(--green-50, #E8F5E9);">
					<span style="font-size: 14px; font-weight: 600; color: var(--green-600);">
						${__("All signatures received. Submit this document to confirm.")}
					</span>
				</div>` : ""}
			</div>
		`);

		// Resend handler
		dialog.$body.find(".resend-btn").on("click", function () {
			const $btn = $(this);
			const child_name = $btn.data("name");
			$btn.prop("disabled", true).text(__("Sending..."));

			frappe.call({
				method: "emsigner.emsigner.api.request_sign.resend_reminder",
				args: {
					doctype: frm.doc.doctype,
					docname: frm.doc.name,
					child_name: child_name,
				},
				callback(r) {
					const msg = (r.message && r.message.message) || __("Reminder sent");
					frappe.show_alert({ message: msg, indicator: "green" }, 3);
					$btn.text(__("Sent"));
				},
				error() {
					$btn.prop("disabled", false).text(__("Resend"));
					frappe.show_alert({ message: __("Failed to send"), indicator: "red" }, 3);
				},
			});
		});

		dialog.show();
	}

	// Pre-sign Preview & Send

	function validate_and_send_sign_request(frm) {
		const pending = (frm.doc.signatory_detail || []).filter(
			(s) => s.signature_status === "Not Initiated" || s.signature_status === "Failure"
		);

		if (!pending.length) {
			frappe.show_alert(
				{ message: __("No pending signatories to send requests to"), indicator: "orange" },
				5
			);
			return;
		}

		frappe.call({
			method: "emsigner.emsigner.api.make_sign.preview_before_signing",
			args: { doctype: frm.doc.doctype, docname: frm.doc.name },
			freeze: true,
			freeze_message: __("Generating document preview..."),
			callback(r) {
				const data = r.message || {};
				if (!data.pending || !data.pending.length) {
					frappe.show_alert(
						{ message: __("No pending signatories found"), indicator: "orange" }, 5
					);
					return;
				}
				show_pre_sign_preview(frm, data);
			},
			error() {
				frappe.confirm(
					__("Could not generate preview. Send signing requests without previewing?"),
					() => send_sign_request(frm)
				);
			},
		});
	}

	function show_pre_sign_preview(frm, data) {
		const { pdf_base64, page_count, pending, warnings } = data;

		// Assign a color to each signatory for visual distinction
		const SIGNATORY_COLORS = [
			{ bg: "rgba(55,125,255,0.15)", border: "var(--primary)", text: "var(--primary)" },
			{ bg: "rgba(40,167,69,0.15)", border: "#28a745", text: "#28a745" },
			{ bg: "rgba(255,193,7,0.20)", border: "#e6a100", text: "#856404" },
			{ bg: "rgba(220,53,69,0.15)", border: "#dc3545", text: "#dc3545" },
			{ bg: "rgba(111,66,193,0.15)", border: "#6f42c1", text: "#6f42c1" },
			{ bg: "rgba(23,162,184,0.15)", border: "#17a2b8", text: "#17a2b8" },
		];

		// Build warnings HTML
		let warnings_html = "";
		if (warnings && warnings.length) {
			const items = warnings.map(
				(w) => `<li>${frappe.utils.escape_html(w)}</li>`
			).join("");
			warnings_html = `
				<div class="warnings-banner" style="display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; background: var(--yellow-50, #FFF9E6); border: 1px solid var(--yellow-200, #FFE69C); border-radius: 6px; font-size: 12px; text-align: left;">
					<span style="font-size: 18px; line-height: 1;">&#9888;</span>
					<div>
						<strong>${__("Issues detected:")}</strong>
						<ul style="margin: 4px 0 0 16px; padding: 0;">${items}</ul>
					</div>
				</div>
			`;
		}

		// Track updates per signatory index: { coords, select_page, page_number, sign_position }
		const sig_updates = {};
		pending.forEach((s, i) => {
			sig_updates[i] = {
				coords: s.customize_coordinates || "",
				select_page: s.select_page || "",
				page_number: s.page_number || "",
				sign_position: s.sign_position || "",
			};
		});

		// Build page options for select dropdown
		function build_page_options(selected) {
			const opts = ["ALL", "FIRST", "LAST", "EVEN", "ODD", "SPECIFY"];
			return opts.map(
				(o) => `<option value="${o}" ${o === selected ? "selected" : ""}>${o.charAt(0) + o.slice(1).toLowerCase()}</option>`
			).join("");
		}

		// Build signatory card data
		const signatory_cards = pending.map((s, i) => {
			const color = SIGNATORY_COLORS[i % SIGNATORY_COLORS.length];
			const name = frappe.utils.escape_html(s.signatory_name);
			const is_custom = s.sign_position === "Customize";
			const pos_label = is_custom
				? (s.customize_coordinates ? __("Custom position") : __("No coordinates set"))
				: (s.sign_position || __("Not set"));
			const specify_display = s.select_page === "SPECIFY" ? "" : "display: none;";
			return `<div class="sig-card" data-index="${i}" data-is-custom="${is_custom ? 1 : 0}"
				style="padding: 10px 12px; border: 2px solid transparent; border-radius: 8px; cursor: pointer; transition: all 0.15s ease;">
				<div style="display: flex; align-items: center; gap: 10px;">
					<span style="display: inline-block; width: 18px; height: 18px; flex-shrink: 0;
						background: ${color.bg}; border: 2px dashed ${color.border}; border-radius: 4px;"></span>
					<div style="flex: 1; min-width: 0;">
						<div style="font-weight: 600; font-size: 13px; color: var(--heading-color);">${name}</div>
						<div class="sig-card-detail" style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">${pos_label}</div>
					</div>
					<span style="font-size: 11px; color: var(--text-muted);">&#8594;</span>
				</div>
					<div style="margin-top: 8px; display: flex; flex-direction: column; gap: 4px;" onclick="event.stopPropagation();">
					<select class="sig-page-select form-control input-xs" data-index="${i}" style="font-size: 11px; height: 26px; padding: 2px 6px;">
						${build_page_options(s.select_page || "ALL")}
					</select>
					<input type="number" class="sig-page-number form-control input-xs" data-index="${i}" placeholder="${__("Page #")}"
						value="${s.page_number || ""}" min="1" style="font-size: 11px; height: 26px; padding: 2px 6px; ${specify_display}" />
				</div>
			</div>`;
		}).join("");

		// Build overlay divs for all signatories
		const overlays = pending.map((s, i) => {
			const color = SIGNATORY_COLORS[i % SIGNATORY_COLORS.length];
			const name = frappe.utils.escape_html(s.signatory_name);
			const is_custom = s.sign_position === "Customize";
			const has_coords = is_custom && !!s.customize_coordinates;
			return `<div class="sig-overlay" data-sig-index="${i}"
				data-sign-position="${frappe.utils.escape_html(s.sign_position || "")}"
				data-coords="${frappe.utils.escape_html(s.customize_coordinates || "")}"
				data-select-page="${frappe.utils.escape_html(s.select_page || "ALL")}"
				data-page-number="${frappe.utils.escape_html(s.page_number || "")}"
				style="
				position: absolute; padding: 6px 12px;
				background: ${color.bg}; border: 2px dashed ${color.border};
				border-radius: 4px; cursor: ${is_custom ? "grab" : "default"};
				font-size: 11px; font-weight: 600; color: ${color.text};
				z-index: 10; display: none;
				white-space: nowrap; user-select: none;
				${is_custom && !has_coords ? "left: 20px; top: 20px;" : ""}
			">${name}</div>`;
		}).join("");

		const dialog = new frappe.ui.Dialog({
			title: __("Verify & Adjust Signature Positions — {0}", [frm.doc.name]),
			size: "extra-large",
			primary_action_label: __("Confirm & Send"),
			primary_action() {
				// Save any updated coordinates/page settings before sending
				save_updated_coordinates(frm, pending, sig_updates, () => {
					dialog.hide();
					send_sign_request(frm);
				});
			},
			secondary_action_label: __("Cancel"),
			secondary_action() {
				dialog.hide();
			},
		});

		dialog.$body.html(`
			<div class="pre-sign-container" style="display: flex; gap: 16px; padding: 4px 0; align-items: flex-start;">
				<div class="sig-sidebar" style="width: 220px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px;">
					<div style="display: flex; align-items: center; justify-content: space-between; padding: 0 4px;">
						<div style="font-weight: 600; font-size: 12px; color: var(--heading-color); text-transform: uppercase; letter-spacing: 0.5px;">
							${__("Signatories")}
						</div>
						<button class="btn btn-xs btn-default add-signatory-btn" title="${__("Add External Signatory")}">+ ${__("Add")}</button>
					</div>
					<div class="sig-cards-list" style="display: flex; flex-direction: column; gap: 4px;">
						${signatory_cards}
					</div>
					${warnings_html ? `<div style="margin-top: 4px;">${warnings_html}</div>` : ""}
					<div class="text-muted" style="font-size: 11px; padding: 4px;">
						${__("Click a signatory to navigate. Drag their box on the PDF to reposition.")}
					</div>
				</div>
				<div class="pdf-section" style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 10px; min-width: 0;">
					<div style="display: flex; align-items: center; gap: 12px;">
						<button class="btn btn-xs btn-default prev-page" disabled>&laquo; Prev</button>
						<span class="page-info text-muted" style="font-size: 13px;">Page 1 / ${page_count || 1}</span>
						<button class="btn btn-xs btn-default next-page" disabled>Next &raquo;</button>
					</div>
					<div class="pdf-viewer-wrapper" style="position: relative; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--fg-color); box-shadow: var(--shadow-sm);">
						<canvas class="pdf-canvas" style="display: block; position: relative; z-index: 1;"></canvas>
						${overlays}
					</div>
				</div>
			</div>
		`);

		const $container = dialog.$body.find(".pre-sign-container");
		const $canvas = $container.find(".pdf-canvas");
		const $wrapper = $container.find(".pdf-viewer-wrapper");
		const $prevBtn = $container.find(".prev-page");
		const $nextBtn = $container.find(".next-page");
		const $pageInfo = $container.find(".page-info");
		const canvas = $canvas[0];

		let current_page = 1;
		let total_pages = 1;
		let pdf_doc = null;
		let pdf_width = 0;
		let pdf_height = 0;
		let active_sig_index = -1;
		let current_display_scale = 1;

		// Drag state
		let isDragging = false;
		let drag$el = null;
		let dragOffsetX = 0;
		let dragOffsetY = 0;

		load_pdfjs().then(() => {
			try {
				const pdfData = atob(pdf_base64);
				pdfjsLib.getDocument({ data: pdfData }).promise.then((pdf) => {
					pdf_doc = pdf;
					total_pages = pdf.numPages;
					$pageInfo.text(`Page ${current_page} / ${total_pages}`);
					$prevBtn.prop("disabled", current_page <= 1);
					$nextBtn.prop("disabled", current_page >= total_pages);
					render_preview_page(current_page);
				}).catch(() => {
					frappe.show_alert({ message: __("Failed to load PDF preview"), indicator: "red" }, 5);
				});
			} catch (e) {
				frappe.show_alert({ message: __("Invalid PDF data"), indicator: "red" }, 5);
			}
		});

		$prevBtn.on("click", () => {
			if (current_page > 1) { current_page--; render_preview_page(current_page); }
		});
		$nextBtn.on("click", () => {
			if (current_page < total_pages) { current_page++; render_preview_page(current_page); }
		});

		// Click a signatory card → navigate to their page and select
		$container.find(".sig-card").on("click", function () {
			const idx = parseInt($(this).data("index"));
			select_signatory(idx);
		});

		// Page select dropdown changed
		$container.on("change", ".sig-page-select", function (e) {
			const idx = parseInt($(this).data("index"));
			const val = $(this).val();
			sig_updates[idx].select_page = val;

			// Update the overlay's jQuery data cache (not attr)
			const $overlay = $wrapper.find(`.sig-overlay[data-sig-index="${idx}"]`);
			$overlay.data("select-page", val);

			// Show/hide page number input
			const $numInput = $container.find(`.sig-page-number[data-index="${idx}"]`);
			if (val === "SPECIFY") {
				$numInput.show();
			} else {
				$numInput.hide();
			}

			// Navigate to the target page for this signatory and re-render
			const targetPage = get_target_page_for_index(idx);
			current_page = targetPage;
			active_sig_index = idx;
			$container.find(".sig-card").css({ "border-color": "transparent", "background": "none" });
			$container.find(`.sig-card[data-index="${idx}"]`).css({
				"border-color": "var(--primary)", "background": "var(--subtle-fg)",
			});
			render_preview_page(current_page);
		});

		// Page number input changed
		$container.on("input", ".sig-page-number", function () {
			const idx = parseInt($(this).data("index"));
			const val = $(this).val();
			sig_updates[idx].page_number = val;
			$wrapper.find(`.sig-overlay[data-sig-index="${idx}"]`).data("page-number", val);

			const targetPage = get_target_page_for_index(idx);
			current_page = targetPage;
			render_preview_page(current_page);
		});

		function select_signatory(idx) {
			active_sig_index = idx;
			$container.find(".sig-card").css({ "border-color": "transparent", "background": "none" });
			$container.find(`.sig-card[data-index="${idx}"]`).css({
				"border-color": "var(--primary)", "background": "var(--subtle-fg)",
			});

			const targetPage = get_target_page_for_index(idx);
			if (targetPage !== current_page) {
				current_page = targetPage;
				render_preview_page(current_page);
			} else {
				update_overlay_styles();
			}
		}

		// Drag: mousedown on overlay — dragging a preset position converts it to Customize
		$wrapper.on("mousedown", ".sig-overlay", function (e) {
			const sigIdx = parseInt($(this).data("sig-index"));
			select_signatory(sigIdx);

			isDragging = true;
			drag$el = $(this);
			drag$el.css("cursor", "grabbing");
			dragOffsetX = e.clientX - this.getBoundingClientRect().left;
			dragOffsetY = e.clientY - this.getBoundingClientRect().top;
			e.preventDefault();
		});

		$(document).on("mousemove.pre_sign", (e) => {
			if (!isDragging || !drag$el) return;
			const rect = $wrapper[0].getBoundingClientRect();
			let x = e.clientX - rect.left - dragOffsetX;
			let y = e.clientY - rect.top - dragOffsetY;
			x = Math.max(0, Math.min(x, pdf_width - drag$el.outerWidth()));
			y = Math.max(0, Math.min(y, pdf_height - drag$el.outerHeight()));
			drag$el.css({ left: x, top: y });

			const ds = current_display_scale || 1;
			const sigIdx = parseInt(drag$el.data("sig-index"));
			const w = drag$el.outerWidth() / ds;
			const h = drag$el.outerHeight() / ds;
			const coords = [
				(x / ds).toFixed(2),
				((pdf_height - y) / ds).toFixed(2),
				w.toFixed(2),
				h.toFixed(2),
			].join(",");
			sig_updates[sigIdx].coords = coords;
			drag$el.data("coords", coords);

			// Convert preset position to Customize on drag
			if (drag$el.data("sign-position") !== "Customize") {
				drag$el.data("sign-position", "Customize");
				drag$el.css("cursor", "grabbing");
				sig_updates[sigIdx].sign_position = "Customize";
				pending[sigIdx].sign_position = "Customize";
			}

			$container.find(`.sig-card[data-index="${sigIdx}"] .sig-card-detail`).text(
				__("Custom position") + " (" + __("moved") + ")"
			);
		});

		$(document).on("mouseup.pre_sign", () => {
			if (isDragging && drag$el) {
				drag$el.css("cursor", "grab");
				isDragging = false;
				drag$el = null;
			}
		});

		dialog.onhide = () => {
			$(document).off("mousemove.pre_sign");
			$(document).off("mouseup.pre_sign");
			isDragging = false;
			drag$el = null;
		};

		function get_target_page_for_index(idx) {
			const u = sig_updates[idx] || {};
			const selectPage = (u.select_page || "").toUpperCase();
			const specifiedPage = parseInt(u.page_number) || 0;
			switch (selectPage) {
				case "FIRST": return 1;
				case "LAST": return total_pages;
				case "SPECIFY": return Math.min(specifiedPage, total_pages) || 1;
				case "ALL": return current_page;
				case "EVEN": return current_page % 2 === 0 ? current_page : Math.min(2, total_pages);
				case "ODD": return current_page % 2 === 1 ? current_page : 1;
				default: return current_page;
			}
		}

		function update_overlay_styles() {
			$wrapper.find(".sig-overlay").each(function () {
				const sigIdx = parseInt($(this).data("sig-index"));
				if (sigIdx === active_sig_index) {
					$(this).css({ "box-shadow": "0 0 0 3px var(--primary)", "z-index": 20, "opacity": 1 });
				} else {
					$(this).css({ "box-shadow": "none", "z-index": 10, "opacity": 0.6 });
				}
			});
		}

		function should_show_on_page($el, pageNum, totalPages) {
			const selectPage = String($el.data("select-page") || "").toUpperCase();
			const specifiedPage = parseInt($el.data("page-number")) || 0;
			switch (selectPage) {
				case "ALL": return true;
				case "FIRST": return pageNum === 1;
				case "LAST": return pageNum === totalPages;
				case "EVEN": return pageNum % 2 === 0;
				case "ODD": return pageNum % 2 === 1;
				case "SPECIFY": return pageNum === specifiedPage;
				default: return true;
			}
		}

		function get_preset_position(position, width, height) {
			const margin = 10;
			const positions = {
				"Top-Left":      { x: margin,                  y: margin },
				"Top-Center":    { x: width * 0.35,            y: margin },
				"Top-Right":     { x: width * 0.7,             y: margin },
				"Middle-Left":   { x: margin,                  y: height * 0.45 },
				"Middle-Center": { x: width * 0.35,            y: height * 0.45 },
				"Middle-Right":  { x: width * 0.7,             y: height * 0.45 },
				"Bottom-Left":   { x: margin,                  y: height * 0.88 },
				"Bottom-Center": { x: width * 0.35,            y: height * 0.88 },
				"Bottom-Right":  { x: width * 0.7,             y: height * 0.88 },
			};
			return positions[position] || { x: margin, y: margin };
		}

		function render_preview_page(pageNum) {
			if (!pdf_doc) return;
			pdf_doc.getPage(pageNum).then((page) => {
				const viewport = page.getViewport({ scale: 1.0 });
				const maxWidth = 700;
				const displayScale = Math.min(1, maxWidth / viewport.width);
				current_display_scale = displayScale;
				const scaledViewport = page.getViewport({ scale: displayScale });

				canvas.width = scaledViewport.width;
				canvas.height = scaledViewport.height;
				pdf_width = scaledViewport.width;
				pdf_height = scaledViewport.height;
				$wrapper.css({ width: scaledViewport.width, height: scaledViewport.height });

				page.render({ canvasContext: canvas.getContext("2d"), viewport: scaledViewport }).promise.then(() => {
					$wrapper.find(".sig-overlay").each(function () {
						const $el = $(this);
						if (!should_show_on_page($el, pageNum, total_pages)) {
							$el.css("display", "none");
							return;
						}

						const signPosition = $el.data("sign-position");
						const is_custom = signPosition === "Customize";

						if (is_custom) {
							const coordsStr = $el.data("coords");
							if (!coordsStr) {
								$el.css({ display: "flex", "align-items": "center" });
								return;
							}
							const parts = String(coordsStr).split(",").map(Number);
							if (parts.length !== 4 || parts.some(isNaN)) return;
							const [gx, gy, gw, gh] = parts;
							$el.css({
								left: gx * displayScale,
								top: pdf_height - gy * displayScale,
								width: gw * displayScale,
								height: gh * displayScale,
								display: "flex",
								"align-items": "center",
								"justify-content": "center",
							});
						} else {
							// Preset position — place at approximate location
							const pos = get_preset_position(signPosition, pdf_width, pdf_height);
							$el.css({
								left: pos.x,
								top: pos.y,
								display: "flex",
								"align-items": "center",
							});
						}
					});
					update_overlay_styles();
				});

				$pageInfo.text(`Page ${pageNum} / ${total_pages}`);
				$prevBtn.prop("disabled", pageNum <= 1);
				$nextBtn.prop("disabled", pageNum >= total_pages);
			});
		}

		// Add External Signatory button handler
		dialog.$body.find(".add-signatory-btn").on("click", () => {
			frappe.prompt(
				[
					{
						label: __("Signatory Name"),
						fieldname: "signatory_name",
						fieldtype: "Data",
						reqd: 1,
					},
					{
						label: __("Signatory Email"),
						fieldname: "signatory_email",
						fieldtype: "Data",
						options: "Email",
						reqd: 1,
					},
					{
						fieldtype: "Column Break",
					},
					{
						label: __("Sign Position"),
						fieldname: "sign_position",
						fieldtype: "Select",
						options: "Top-Left\nTop-Center\nTop-Right\nMiddle-Left\nMiddle-Center\nMiddle-Right\nBottom-Left\nBottom-Center\nBottom-Right\nCustomize",
						reqd: 1,
						default: "Bottom-Left",
					},
					{
						label: __("Select Page"),
						fieldname: "select_page",
						fieldtype: "Select",
						options: "ALL\nFIRST\nEVEN\nLAST\nODD\nSPECIFY",
						reqd: 1,
						default: "ALL",
					},
					{
						label: __("Page Number"),
						fieldname: "page_number",
						fieldtype: "Int",
						depends_on: "eval: doc.select_page == 'SPECIFY'",
						mandatory_depends_on: "eval: doc.select_page == 'SPECIFY'",
					},
				],
				(values) => {
					frappe.call({
						method: "emsigner.emsigner.api.request_sign.add_external_signatory",
						args: {
							doctype: frm.doc.doctype,
							docname: frm.doc.name,
							signatory_name: values.signatory_name,
							signatory_email: values.signatory_email,
							sign_position: values.sign_position,
							select_page: values.select_page,
							page_number: values.page_number || "",
						},
						freeze: true,
						freeze_message: __("Adding signatory..."),
						callback() {
							frappe.show_alert(
								{ message: __("Signatory added. Refreshing preview..."), indicator: "green" },
								3
							);
							dialog.hide();
							frm.reload_doc().then(() => {
								validate_and_send_sign_request(frm);
							});
						},
					});
				},
				__("Add External Signatory"),
				__("Add")
			);
		});

		dialog.show();
	}

	function save_updated_coordinates(frm, pending, sig_updates, callback) {
		const updates = [];
		for (const [idx, u] of Object.entries(sig_updates)) {
			const s = pending[parseInt(idx)];
			if (!s || !s.child_name) continue;

			// Include if position was converted to Customize or if coords/page changed
			const position_converted = u.sign_position === "Customize" && s.sign_position !== "Customize";
			const is_customize = u.sign_position === "Customize" || s.sign_position === "Customize";
			if (!is_customize) continue;

			const coords_changed = u.coords && u.coords !== s.customize_coordinates;
			const page_changed = u.select_page !== (s.select_page || "");
			const pagenum_changed = String(u.page_number || "") !== String(s.page_number || "");

			if (position_converted || coords_changed || page_changed || pagenum_changed) {
				updates.push({
					child_name: s.child_name,
					coordinates: u.coords || s.customize_coordinates,
					select_page: u.select_page || s.select_page,
					page_number: u.page_number || "",
					sign_position: u.sign_position || s.sign_position,
				});
			}
		}

		if (!updates.length) {
			callback();
			return;
		}

		const promises = updates.map((u) =>
			frappe.xcall("emsigner.emsigner.api.request_sign.update_coordinates_value", {
				child_doctype: "emSigner Signatory Detail",
				child_name: u.child_name,
				coordinates: u.coordinates,
				select_page: u.select_page,
				page_number: u.page_number,
				sign_position: u.sign_position,
			})
		);

		Promise.all(promises).then(() => {
			frappe.show_alert(
				{ message: __("{0} signature position(s) updated", [updates.length]), indicator: "blue" }, 3
			);
			callback();
		}).catch(() => {
			frappe.show_alert(
				{ message: __("Failed to save some position updates"), indicator: "red" }, 5
			);
		});
	}

	function send_sign_request(frm) {
		frappe.call({
			method: "emsigner.emsigner.api.request_sign.send_email_request",
			args: { docname: frm.doc.name, doctype: frm.doc.doctype },
			freeze: true,
			freeze_message: __("Sending signature requests..."),
			callback() {
				frappe.show_alert(
					{ message: __("Signature requests sent successfully"), indicator: "green" },
					5
				);
				frm.reload_doc();
			},
			error() {
				frappe.show_alert(
					{ message: __("Failed to send signature requests"), indicator: "red" },
					5
				);
			},
		});
	}

	// Status Indicators

	const STATUS_COLORS = {
		"Not Initiated": "grey",
		"Pending Review": "orange",
		"Review In-Progress": "blue",
		Rejected: "red",
		Failure: "red",
		Completed: "green",
	};

	function apply_status_indicators(frm) {
		if (!frm.fields_dict.signatory_detail) return;

		const grid = frm.fields_dict.signatory_detail.grid;
		if (!grid || !grid.grid_rows) return;

		setTimeout(() => {
			grid.grid_rows.forEach((grid_row) => {
				if (!grid_row.doc) return;
				const status = grid_row.doc.signature_status;
				const color = STATUS_COLORS[status] || "grey";
				const $row = $(grid_row.row);
				const $status_cell = $row.find('[data-field="signature_status"] .static-area');
				if ($status_cell.length && !$status_cell.find(".indicator-pill").length) {
					$status_cell.html(
						`<span class="indicator-pill ${color}">${frappe.utils.escape_html(status || "Not Initiated")}</span>`
					);
				}
			});
		}, 100);
	}

	// Signature Placement Dialog

	function open_signature_placement_dialog(frm, row) {
		if (row.sign_position !== "Customize") {
			frappe.show_alert(
				{ message: __("Set Sign Position to 'Customize' to place signature"), indicator: "orange" },
				5
			);
			return;
		}

		// Collect other signatories on this document who already have coordinates
		const other_signatories = (frm.doc.signatory_detail || []).filter(
			(s) => s.name !== row.name
				&& s.sign_position === "Customize"
				&& s.customize_coordinates
		);

		frappe.call({
			method: "emsigner.emsigner.api.make_sign.download_document_pdf",
			args: {
				doctype: frm.doc.doctype,
				docname: frm.doc.name,
				signatory_details: JSON.stringify(row),
				print_format: frm.doc.requested_print_format || "",
				letter_head: frm.doc.requested_letter_head || "",
			},
			freeze: true,
			freeze_message: __("Generating PDF preview..."),
			callback(r) {
				if (r.message) {
					show_placement_dialog(frm, row, r.message, other_signatories);
				} else {
					frappe.show_alert(
						{ message: __("Failed to load PDF"), indicator: "red" },
						5
					);
				}
			},
		});
	}

	function show_placement_dialog(frm, row, pdf_base64, other_signatories) {
		const SCALE_FACTOR = 1.0;
		let current_page = 1;
		let total_pages = 1;
		let pdf_doc = null;
		let pdf_width = 0;
		let pdf_height = 0;
		let has_dragged = false;
		let signature_coords = { x: 0, y: 0, width: 0, height: 0 };

		// Restore existing coordinates if any
		if (row.customize_coordinates) {
			const parts = row.customize_coordinates.split(",").map(Number);
			if (parts.length === 4 && parts.every((p) => !isNaN(p))) {
				signature_coords = { x: parts[0], y: parts[1], width: parts[2], height: parts[3] };
				has_dragged = true;
			}
		}

		// Build ghost overlay HTML for other signatories
		const ghost_overlays = (other_signatories || []).map((s) => {
			const name = frappe.utils.escape_html(s.signatory_name || "Other");
			return `<div class="ghost-signature" data-coords="${frappe.utils.escape_html(s.customize_coordinates)}" style="
				position: absolute; padding: 6px 12px;
				background: rgba(200, 200, 200, 0.25);
				border: 1px dashed var(--gray-400);
				border-radius: 4px; pointer-events: none;
				font-size: 11px; color: var(--gray-600);
				z-index: 5; display: none;
				white-space: nowrap; overflow: hidden;
			">${name}</div>`;
		}).join("");

		const dialog = new frappe.ui.Dialog({
			title: __("Place Signature — {0}", [row.signatory_name || "Signatory"]),
			size: "extra-large",
			primary_action_label: __("Set Coordinates"),
			primary_action() {
				if (!has_dragged) {
					frappe.show_alert(
						{ message: __("Please drag the signature box to the desired position"), indicator: "orange" },
						5
					);
					return;
				}
				const coords_str = [
					signature_coords.x.toFixed(2),
					signature_coords.y.toFixed(2),
					signature_coords.width.toFixed(2),
					signature_coords.height.toFixed(2),
				].join(",");

				frappe.model.set_value(row.doctype, row.name, "customize_coordinates", coords_str);
				frm.dirty();
				frm.save().then(() => {
					frappe.show_alert(
						{ message: __("Signature coordinates saved"), indicator: "green" },
						5
					);
				});
				dialog.hide();
			},
			secondary_action_label: __("Cancel"),
			secondary_action() {
				dialog.hide();
			},
		});

		dialog.$body.html(`
			<div class="signature-placement-container" style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
				${other_signatories && other_signatories.length ? `
				<div class="legend-bar" style="display: flex; gap: 16px; align-items: center; font-size: 12px; color: var(--text-muted);">
					<span style="display: flex; align-items: center; gap: 4px;">
						<span style="display: inline-block; width: 14px; height: 14px; background: rgba(55,125,255,0.15); border: 2px dashed var(--primary); border-radius: 3px;"></span>
						${__("Your position")}
					</span>
					<span style="display: flex; align-items: center; gap: 4px;">
						<span style="display: inline-block; width: 14px; height: 14px; background: rgba(200,200,200,0.25); border: 1px dashed var(--gray-400); border-radius: 3px;"></span>
						${__("Other signatories")}
					</span>
				</div>
				` : ""}
				<div class="page-controls" style="display: flex; align-items: center; gap: 12px;">
					<button class="btn btn-xs btn-default prev-page" disabled>&laquo; Prev</button>
					<span class="page-info text-muted" style="font-size: 13px;">Page 1 / 1</span>
					<button class="btn btn-xs btn-default next-page" disabled>Next &raquo;</button>
				</div>
				<div class="pdf-viewer-wrapper" style="position: relative; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--fg-color); box-shadow: var(--shadow-sm);">
					<canvas class="pdf-canvas" style="display: block;"></canvas>
					${ghost_overlays}
					<div class="signature-box" style="
						position: absolute; padding: 8px 16px; background: rgba(55, 125, 255, 0.15);
						border: 2px dashed var(--primary); border-radius: 4px; cursor: grab;
						font-size: 13px; font-weight: 500; color: var(--primary);
						user-select: none; z-index: 10; left: 20px; top: 20px;
						display: flex; align-items: center; gap: 6px;
					">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M12 2L12 22M2 12L22 12M7 7L7 7M17 7L17 7M7 17L7 17M17 17L17 17"/>
						</svg>
						${frappe.utils.escape_html(row.signatory_name || "Signature")}
					</div>
				</div>
				<div class="coords-display text-muted" style="font-size: 12px; font-family: var(--font-stack-monospace);">
					Coordinates: —
				</div>
			</div>
		`);

		const $container = dialog.$body.find(".signature-placement-container");
		const $canvas = $container.find(".pdf-canvas");
		const $sigBox = $container.find(".signature-box");
		const $wrapper = $container.find(".pdf-viewer-wrapper");
		const $coordsDisplay = $container.find(".coords-display");
		const $prevBtn = $container.find(".prev-page");
		const $nextBtn = $container.find(".next-page");
		const $pageInfo = $container.find(".page-info");
		const canvas = $canvas[0];

		// Load pdf.js dynamically
		load_pdfjs().then(() => {
			const pdfData = atob(pdf_base64);
			const loadingTask = pdfjsLib.getDocument({ data: pdfData });
			loadingTask.promise.then((pdf) => {
				pdf_doc = pdf;
				total_pages = pdf.numPages;
				$pageInfo.text(`Page ${current_page} / ${total_pages}`);
				$prevBtn.prop("disabled", current_page <= 1);
				$nextBtn.prop("disabled", current_page >= total_pages);
				render_page(current_page);
			});
		});

		$prevBtn.on("click", () => {
			if (current_page > 1) {
				current_page--;
				render_page(current_page);
			}
		});

		$nextBtn.on("click", () => {
			if (current_page < total_pages) {
				current_page++;
				render_page(current_page);
			}
		});

		function position_ghost_overlays(displayScale) {
			$wrapper.find(".ghost-signature").each(function () {
				const coordsStr = $(this).data("coords");
				if (!coordsStr) return;
				const parts = String(coordsStr).split(",").map(Number);
				if (parts.length !== 4 || parts.some(isNaN)) return;
				const [gx, gy, gw, gh] = parts;
				$(this).css({
					left: gx * displayScale,
					top: pdf_height - gy * displayScale,
					width: gw * displayScale,
					height: gh * displayScale,
					display: "flex",
					"align-items": "center",
					"justify-content": "center",
				});
			});
		}

		function render_page(pageNum) {
			pdf_doc.getPage(pageNum).then((page) => {
				const viewport = page.getViewport({ scale: SCALE_FACTOR });

				// Scale to fit dialog width (max ~750px)
				const maxWidth = 750;
				const displayScale = Math.min(1, maxWidth / viewport.width);
				const scaledViewport = page.getViewport({ scale: SCALE_FACTOR * displayScale });

				canvas.width = scaledViewport.width;
				canvas.height = scaledViewport.height;
				pdf_width = scaledViewport.width;
				pdf_height = scaledViewport.height;

				$wrapper.css({ width: scaledViewport.width, height: scaledViewport.height });

				const ctx = canvas.getContext("2d");
				page.render({ canvasContext: ctx, viewport: scaledViewport }).promise.then(() => {
					// Position signature box from saved coords
					if (signature_coords.x || signature_coords.y) {
						const displayX = signature_coords.x * displayScale;
						const displayY = pdf_height - signature_coords.y * displayScale;
						$sigBox.css({ left: displayX, top: displayY });
					}
					position_ghost_overlays(displayScale);
					update_coords_display();
				});

				$pageInfo.text(`Page ${pageNum} / ${total_pages}`);
				$prevBtn.prop("disabled", pageNum <= 1);
				$nextBtn.prop("disabled", pageNum >= total_pages);

				// Store displayScale for drag calculations
				$wrapper.data("displayScale", displayScale);
			});
		}

		// Drag logic
		let isDragging = false;
		let dragOffsetX = 0;
		let dragOffsetY = 0;

		$sigBox.on("mousedown", (e) => {
			isDragging = true;
			$sigBox.css("cursor", "grabbing");
			dragOffsetX = e.clientX - $sigBox[0].getBoundingClientRect().left;
			dragOffsetY = e.clientY - $sigBox[0].getBoundingClientRect().top;
			e.preventDefault();
		});

		$(document).on("mousemove.sig_placement", (e) => {
			if (!isDragging) return;
			const wrapperRect = $wrapper[0].getBoundingClientRect();
			let x = e.clientX - wrapperRect.left - dragOffsetX;
			let y = e.clientY - wrapperRect.top - dragOffsetY;

			// Clamp within bounds
			x = Math.max(0, Math.min(x, pdf_width - $sigBox.outerWidth()));
			y = Math.max(0, Math.min(y, pdf_height - $sigBox.outerHeight()));

			$sigBox.css({ left: x, top: y });

			has_dragged = true;
			const displayScale = $wrapper.data("displayScale") || 1;
			const sigWidth = $sigBox.outerWidth() / displayScale;
			const sigHeight = $sigBox.outerHeight() / displayScale;
			signature_coords = {
				x: x / displayScale,
				y: (pdf_height - y) / displayScale,
				width: sigWidth,
				height: sigHeight,
			};
			update_coords_display();
		});

		$(document).on("mouseup.sig_placement", () => {
			if (isDragging) {
				isDragging = false;
				$sigBox.css("cursor", "grab");
			}
		});

		function update_coords_display() {
			$coordsDisplay.text(
				`Coordinates: x=${signature_coords.x.toFixed(1)}, y=${signature_coords.y.toFixed(1)}, w=${signature_coords.width.toFixed(1)}, h=${signature_coords.height.toFixed(1)}`
			);
		}

		dialog.onhide = () => {
			$(document).off("mousemove.sig_placement");
			$(document).off("mouseup.sig_placement");
		};

		dialog.show();
	}

	// pdf.js Loader

	let pdfjs_loaded = false;

	function load_pdfjs() {
		if (pdfjs_loaded && window.pdfjsLib) {
			return Promise.resolve();
		}
		return new Promise((resolve, reject) => {
			const script = document.createElement("script");
			script.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.min.js";
			script.onload = () => {
				pdfjsLib.GlobalWorkerOptions.workerSrc =
					"https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js";
				pdfjs_loaded = true;
				resolve();
			};
			script.onerror = () => reject(new Error("Failed to load pdf.js"));
			document.head.appendChild(script);
		});
	}
})();
