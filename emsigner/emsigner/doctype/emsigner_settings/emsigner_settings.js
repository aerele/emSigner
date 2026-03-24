// Copyright (c) 2025, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("emSigner Settings", {
	refresh(frm) {
		lock_tables(frm);
		add_management_buttons(frm);
		colorize_signatory_rows(frm);
	},
});

function lock_tables(frm) {
	["authorized_signatory", "print_format"].forEach((field) => {
		const grid = frm.fields_dict[field] && frm.fields_dict[field].grid;
		if (!grid) return;
		grid.cannot_add_rows = true;
		grid.cannot_delete_rows = true;
		grid.cannot_delete_all_rows = true;
		grid.wrapper.find(".grid-add-row, .grid-remove-rows").hide();
	});
}

function add_management_buttons(frm) {
	frm.add_custom_button(__("Setup Doctype"), () => show_setup_doctype_dialog(frm), __("Action"));
	frm.add_custom_button(__("Add Signatory"), () => show_add_signatory_dialog(frm), __("Action"));
	frm.add_custom_button(__("Reposition Signatory"), () => show_reposition_dialog(frm), __("Action"));
	frm.add_custom_button(__("Reset Doctype"), () => show_reset_doctype_dialog(frm), __("Action"));
}

function show_setup_doctype_dialog(frm) {
	const configured = (frm.doc.print_format || []).map((r) => r.permitted_doctype);

	const d = new frappe.ui.Dialog({
		title: __("Setup Doctype for Signing"),
		fields: [
			{
				label: __("Doctype"),
				fieldname: "doctype_name",
				fieldtype: "Link",
				options: "DocType",
				reqd: 1,
				description: configured.length
					? __("Already configured: {0}", [configured.join(", ")])
					: "",
				change() {
					const dt = d.get_value("doctype_name");
					if (configured.includes(dt)) {
						frappe.show_alert({
							message: __("{0} is already configured. Use 'Reset Doctype' first to reconfigure.", [dt]),
							indicator: "orange",
						}, 5);
						d.set_value("doctype_name", "");
					}
					d.fields_dict.print_format.get_query = () => ({
						filters: { doc_type: dt, disabled: 0 },
					});
				},
			},
			{ fieldtype: "Column Break" },
			{
				label: __("Print Format"),
				fieldname: "print_format",
				fieldtype: "Link",
				options: "Print Format",
				reqd: 1,
			},
			{
				label: __("Letter Head"),
				fieldname: "letter_head",
				fieldtype: "Link",
				options: "Letter Head",
			},
			{ fieldtype: "Section Break" },
			{
				label: __("Sample Document"),
				fieldname: "sample_document",
				fieldtype: "Dynamic Link",
				options: "doctype_name",
				reqd: 1,
				description: __("A sample document used for placing signatures. All signatories will use this for positioning."),
			},
		],
		primary_action_label: __("Save Configuration"),
		primary_action(values) {
			if (configured.includes(values.doctype_name)) {
				frappe.throw(__("{0} is already configured.", [values.doctype_name]));
			}

			const row = frm.add_child("print_format");
			row.permitted_doctype = values.doctype_name;
			row.print_format = values.print_format;
			row.letter_head = values.letter_head || "";
			row.sample_document = values.sample_document;

			frm.dirty();
			frm.save().then(() => {
				frappe.show_alert({ message: __("{0} configured successfully", [values.doctype_name]), indicator: "green" }, 5);
			});
			d.hide();
		},
	});
	d.show();
}

function show_add_signatory_dialog(frm) {
	const configs = (frm.doc.print_format || []);
	if (!configs.length) {
		frappe.show_alert({ message: __("No doctypes configured yet. Use 'Setup Doctype' first."), indicator: "orange" }, 5);
		return;
	}

	const doctype_options = configs.map((c) => c.permitted_doctype);

	const d = new frappe.ui.Dialog({
		title: __("Add Signatory"),
		fields: [
			{
				label: __("Doctype"),
				fieldname: "permitted_doctype",
				fieldtype: "Select",
				options: doctype_options.join("\n"),
				reqd: 1,
			},
			{ fieldtype: "Column Break" },
			{
				label: __("Signatory"),
				fieldname: "signatory",
				fieldtype: "Link",
				options: "User",
				reqd: 1,
			},
			{ fieldtype: "Section Break" },
			{
				label: __("Select Page"),
				fieldname: "select_page",
				fieldtype: "Select",
				options: "ALL\nFIRST\nLAST\nEVEN\nODD\nSPECIFY",
				default: "LAST",
				reqd: 1,
			},
			{
				label: __("Page Number"),
				fieldname: "page_number",
				fieldtype: "Data",
				depends_on: "eval: doc.select_page == 'SPECIFY'",
				mandatory_depends_on: "eval: doc.select_page == 'SPECIFY'",
			},
			{ fieldtype: "Column Break" },
			{
				label: __("Sign Position"),
				fieldname: "sign_position",
				fieldtype: "Select",
				options: "Top-Left\nTop-Center\nTop-Right\nMiddle-Left\nMiddle-Center\nMiddle-Right\nBottom-Left\nBottom-Center\nBottom-Right\nCustomize",
				default: "Bottom-Right",
				reqd: 1,
			},
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			frappe.db.get_value("User", values.signatory, ["full_name", "email"]).then((r) => {
				const user = r.message || {};
				const row = frm.add_child("authorized_signatory");
				row.permitted_doctype = values.permitted_doctype;
				row.signatory = values.signatory;
				row.signatory_name = user.full_name || values.signatory;
				row.signatory_email = user.email || values.signatory;
				row.select_page = values.select_page;
				row.page_number = values.page_number || "";
				row.sign_position = values.sign_position;

				d.hide();
				frm.dirty();

				if (values.sign_position === "Customize") {
					frm.save().then(() => {
						frm.reload_doc().then(() => {
							const saved_row = (frm.doc.authorized_signatory || []).find(
								(s) => s.signatory === values.signatory && s.permitted_doctype === values.permitted_doctype && !s.customize_coordinates
							);
							if (saved_row) {
								open_placement_for_row(frm, saved_row);
							}
						});
					});
				} else {
					frm.save().then(() => {
						frappe.show_alert({ message: __("Signatory added"), indicator: "green" }, 3);
						frm.reload_doc();
					});
				}
			});
		},
	});
	d.show();
}

function show_reset_doctype_dialog(frm) {
	const configs = (frm.doc.print_format || []);
	if (!configs.length) {
		frappe.show_alert({ message: __("No doctypes configured."), indicator: "orange" }, 5);
		return;
	}

	const options = configs.map((c) => c.permitted_doctype);

	const d = new frappe.ui.Dialog({
		title: __("Reset Doctype Configuration"),
		fields: [
			{
				label: __("Doctype"),
				fieldname: "doctype_name",
				fieldtype: "Select",
				options: options.join("\n"),
				reqd: 1,
			},
		],
		primary_action_label: __("Reset"),
		primary_action(values) {
			const dt = values.doctype_name;
			const sig_count = (frm.doc.authorized_signatory || []).filter(
				(s) => s.permitted_doctype === dt
			).length;

			frappe.confirm(
				__("This will remove the configuration and {0} signatory(ies) for {1}. Continue?", [sig_count, dt]),
				() => {
					frm.doc.authorized_signatory = (frm.doc.authorized_signatory || []).filter(
						(s) => s.permitted_doctype !== dt
					);
					frm.doc.print_format = (frm.doc.print_format || []).filter(
						(p) => p.permitted_doctype !== dt
					);

					frm.dirty();
					frm.save().then(() => {
						frappe.show_alert({ message: __("{0} configuration reset", [dt]), indicator: "green" }, 5);
						frm.reload_doc();
					});
					d.hide();
				}
			);
		},
	});
	d.show();
}

function show_reposition_dialog(frm) {
	const configs = (frm.doc.print_format || []);
	if (!configs.length) {
		frappe.show_alert({ message: __("No doctypes configured yet."), indicator: "orange" }, 5);
		return;
	}

	const signatories = (frm.doc.authorized_signatory || []);
	if (!signatories.length) {
		frappe.show_alert({ message: __("No signatories to reposition."), indicator: "orange" }, 5);
		return;
	}

	const doctypes_with_sigs = [...new Set(signatories.map((s) => s.permitted_doctype))];

	if (doctypes_with_sigs.length === 1) {
		load_reposition_preview(frm, doctypes_with_sigs[0]);
	} else {
		const d = new frappe.ui.Dialog({
			title: __("Select Doctype"),
			fields: [{
				label: __("Doctype"),
				fieldname: "doctype_name",
				fieldtype: "Select",
				options: doctypes_with_sigs.join("\n"),
				reqd: 1,
			}],
			primary_action_label: __("Continue"),
			primary_action(values) {
				d.hide();
				load_reposition_preview(frm, values.doctype_name);
			},
		});
		d.show();
	}
}

function load_reposition_preview(frm, doctype_name) {
	const config = (frm.doc.print_format || []).find((c) => c.permitted_doctype === doctype_name);
	if (!config || !config.sample_document) {
		frappe.show_alert({ message: __("No sample document configured for {0}.", [doctype_name]), indicator: "orange" }, 5);
		return;
	}

	const sigs = (frm.doc.authorized_signatory || []).filter(
		(s) => s.permitted_doctype === doctype_name && s.sign_position === "Customize"
	);
	if (!sigs.length) {
		frappe.show_alert({ message: __("No signatories with 'Customize' position for {0}.", [doctype_name]), indicator: "orange" }, 5);
		return;
	}

	frappe.call({
		method: "emsigner.emsigner.api.make_sign.download_document_pdf",
		args: {
			doctype: doctype_name,
			docname: config.sample_document,
			signatory_details: JSON.stringify(sigs[0]),
			print_format: config.print_format || "",
			letter_head: config.letter_head || "",
		},
		freeze: true,
		freeze_message: __("Loading {0}...", [config.sample_document]),
		callback(r) {
			if (r.message) {
				show_reposition_preview(frm, sigs, r.message, config);
			} else {
				frappe.show_alert({ message: __("Failed to generate PDF"), indicator: "red" }, 5);
			}
		},
	});
}

function show_reposition_preview(frm, sigs, pdf_base64, config) {
	const SIGNATORY_COLORS = [
		{ bg: "rgba(55,125,255,0.15)", border: "var(--primary)", text: "var(--primary)" },
		{ bg: "rgba(40,167,69,0.15)", border: "#28a745", text: "#28a745" },
		{ bg: "rgba(255,193,7,0.20)", border: "#e6a100", text: "#856404" },
		{ bg: "rgba(220,53,69,0.15)", border: "#dc3545", text: "#dc3545" },
		{ bg: "rgba(111,66,193,0.15)", border: "#6f42c1", text: "#6f42c1" },
		{ bg: "rgba(23,162,184,0.15)", border: "#17a2b8", text: "#17a2b8" },
	];

	const sig_updates = {};
	sigs.forEach((s, i) => {
		sig_updates[i] = {
			coords: s.customize_coordinates || "",
			select_page: s.select_page || "ALL",
			page_number: s.page_number || "",
		};
	});

	function build_page_options(selected) {
		const opts = ["ALL", "FIRST", "LAST", "EVEN", "ODD", "SPECIFY"];
		return opts.map(
			(o) => `<option value="${o}" ${o === selected ? "selected" : ""}>${o.charAt(0) + o.slice(1).toLowerCase()}</option>`
		).join("");
	}

	const cards_html = sigs.map((s, i) => {
		const color = SIGNATORY_COLORS[i % SIGNATORY_COLORS.length];
		const name = frappe.utils.escape_html(s.signatory_name);
		const specify_display = s.select_page === "SPECIFY" ? "" : "display: none;";
		return `<div class="sig-card" data-index="${i}" style="padding: 10px 12px; border: 2px solid transparent; border-radius: 8px; cursor: pointer; transition: all 0.15s ease;">
			<div style="display: flex; align-items: center; gap: 10px;">
				<span style="display: inline-block; width: 18px; height: 18px; flex-shrink: 0; background: ${color.bg}; border: 2px dashed ${color.border}; border-radius: 4px;"></span>
				<div style="flex: 1; min-width: 0;">
					<div style="font-weight: 600; font-size: 13px; color: var(--heading-color);">${name}</div>
					<div class="sig-card-detail" style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
						${s.customize_coordinates ? __("Custom position") : __("No coordinates")}
					</div>
				</div>
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

	const overlays_html = sigs.map((s, i) => {
		const color = SIGNATORY_COLORS[i % SIGNATORY_COLORS.length];
		const name = frappe.utils.escape_html(s.signatory_name);
		const has_coords = !!s.customize_coordinates;
		return `<div class="sig-overlay" data-sig-index="${i}"
			data-coords="${frappe.utils.escape_html(s.customize_coordinates || "")}"
			data-select-page="${frappe.utils.escape_html(s.select_page || "ALL")}"
			data-page-number="${frappe.utils.escape_html(s.page_number || "")}"
			style="position: absolute; padding: 6px 12px; background: ${color.bg}; border: 2px dashed ${color.border};
			border-radius: 4px; cursor: grab; font-size: 11px; font-weight: 600; color: ${color.text};
			z-index: 10; display: none; white-space: nowrap; user-select: none;
			${!has_coords ? "left: 20px; top: 20px;" : ""}">${name}</div>`;
	}).join("");

	const dialog = new frappe.ui.Dialog({
		title: __("Reposition Signatories — {0}", [config.permitted_doctype]),
		size: "extra-large",
		primary_action_label: __("Save Positions"),
		primary_action() {
			save_reposition_updates(frm, sigs, sig_updates, () => {
				dialog.hide();
				frm.reload_doc();
			});
		},
		secondary_action_label: __("Cancel"),
		secondary_action() { dialog.hide(); },
	});

	dialog.$body.html(`
		<div class="reposition-container" style="display: flex; gap: 16px; padding: 4px 0; align-items: flex-start;">
			<div class="sig-sidebar" style="width: 220px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px;">
				<div style="font-weight: 600; font-size: 12px; color: var(--heading-color); padding: 0 4px; text-transform: uppercase; letter-spacing: 0.5px;">
					${__("Signatories")}
				</div>
				<div class="sig-cards-list" style="display: flex; flex-direction: column; gap: 4px;">
					${cards_html}
				</div>
				<div class="text-muted" style="font-size: 11px; padding: 4px;">
					${__("Click a signatory to navigate. Drag their box on the PDF to reposition.")}
				</div>
			</div>
			<div class="pdf-section" style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 10px; min-width: 0;">
				<div style="font-size: 12px; color: var(--text-muted);">
					${__("Sample")}: <strong>${frappe.utils.escape_html(config.sample_document)}</strong>
					&middot; ${__("Format")}: <strong>${frappe.utils.escape_html(config.print_format || "Standard")}</strong>
				</div>
				<div style="display: flex; align-items: center; gap: 12px;">
					<button class="btn btn-xs btn-default prev-page" disabled>&laquo; Prev</button>
					<span class="page-info text-muted" style="font-size: 13px;">Page 1 / 1</span>
					<button class="btn btn-xs btn-default next-page" disabled>Next &raquo;</button>
				</div>
				<div class="pdf-viewer-wrapper" style="position: relative; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--fg-color); box-shadow: var(--shadow-sm);">
					<canvas class="pdf-canvas" style="display: block; position: relative; z-index: 1;"></canvas>
					${overlays_html}
				</div>
			</div>
		</div>
	`);

	const $container = dialog.$body.find(".reposition-container");
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
	let isDragging = false;
	let drag$el = null;
	let dragOffsetX = 0;
	let dragOffsetY = 0;

	load_pdfjs_if_needed().then(() => {
		const pdfData = atob(pdf_base64);
		pdfjsLib.getDocument({ data: pdfData }).promise.then((pdf) => {
			pdf_doc = pdf;
			total_pages = pdf.numPages;
			$pageInfo.text(`Page ${current_page} / ${total_pages}`);
			$prevBtn.prop("disabled", current_page <= 1);
			$nextBtn.prop("disabled", current_page >= total_pages);
			render_page(current_page);
		});
	});

	$prevBtn.on("click", () => { if (current_page > 1) { current_page--; render_page(current_page); } });
	$nextBtn.on("click", () => { if (current_page < total_pages) { current_page++; render_page(current_page); } });

	$container.find(".sig-card").on("click", function () {
		const idx = parseInt($(this).data("index"));
		select_sig(idx);
	});

	$container.on("change", ".sig-page-select", function () {
		const idx = parseInt($(this).data("index"));
		const val = $(this).val();
		sig_updates[idx].select_page = val;
		$wrapper.find(`.sig-overlay[data-sig-index="${idx}"]`).data("select-page", val);

		const $numInput = $container.find(`.sig-page-number[data-index="${idx}"]`);
		if (val === "SPECIFY") { $numInput.show(); } else { $numInput.hide(); }

		const targetPage = get_target_page(idx);
		current_page = targetPage;
		active_sig_index = idx;
		highlight_card(idx);
		render_page(current_page);
	});

	$container.on("input", ".sig-page-number", function () {
		const idx = parseInt($(this).data("index"));
		const val = $(this).val();
		sig_updates[idx].page_number = val;
		$wrapper.find(`.sig-overlay[data-sig-index="${idx}"]`).data("page-number", val);
		current_page = get_target_page(idx);
		render_page(current_page);
	});

	$wrapper.on("mousedown", ".sig-overlay", function (e) {
		const sigIdx = parseInt($(this).data("sig-index"));
		select_sig(sigIdx);
		isDragging = true;
		drag$el = $(this);
		drag$el.css("cursor", "grabbing");
		dragOffsetX = e.clientX - this.getBoundingClientRect().left;
		dragOffsetY = e.clientY - this.getBoundingClientRect().top;
		e.preventDefault();
	});

	$(document).on("mousemove.reposition", (e) => {
		if (!isDragging || !drag$el) return;
		const rect = $wrapper[0].getBoundingClientRect();
		let x = e.clientX - rect.left - dragOffsetX;
		let y = e.clientY - rect.top - dragOffsetY;
		x = Math.max(0, Math.min(x, pdf_width - drag$el.outerWidth()));
		y = Math.max(0, Math.min(y, pdf_height - drag$el.outerHeight()));
		drag$el.css({ left: x, top: y });

		const ds = current_display_scale || 1;
		const sigIdx = parseInt(drag$el.data("sig-index"));
		const coords = [
			(x / ds).toFixed(2),
			((pdf_height - y) / ds).toFixed(2),
			(drag$el.outerWidth() / ds).toFixed(2),
			(drag$el.outerHeight() / ds).toFixed(2),
		].join(",");
		sig_updates[sigIdx].coords = coords;
		drag$el.data("coords", coords);

		$container.find(`.sig-card[data-index="${sigIdx}"] .sig-card-detail`).text(
			__("Custom position") + " (" + __("moved") + ")"
		);
	});

	$(document).on("mouseup.reposition", () => {
		if (isDragging && drag$el) { drag$el.css("cursor", "grab"); isDragging = false; drag$el = null; }
	});

	dialog.onhide = () => {
		$(document).off("mousemove.reposition");
		$(document).off("mouseup.reposition");
	};

	function select_sig(idx) {
		active_sig_index = idx;
		highlight_card(idx);
		const targetPage = get_target_page(idx);
		if (targetPage !== current_page) {
			current_page = targetPage;
			render_page(current_page);
		} else {
			update_overlay_styles();
		}
	}

	function highlight_card(idx) {
		$container.find(".sig-card").css({ "border-color": "transparent", "background": "none" });
		$container.find(`.sig-card[data-index="${idx}"]`).css({
			"border-color": "var(--primary)", "background": "var(--subtle-fg)",
		});
	}

	function get_target_page(idx) {
		const u = sig_updates[idx] || {};
		const sp = (u.select_page || "").toUpperCase();
		const pn = parseInt(u.page_number) || 0;
		switch (sp) {
			case "FIRST": return 1;
			case "LAST": return total_pages;
			case "SPECIFY": return Math.min(pn, total_pages) || 1;
			case "ALL": return current_page;
			case "EVEN": return current_page % 2 === 0 ? current_page : Math.min(2, total_pages);
			case "ODD": return current_page % 2 === 1 ? current_page : 1;
			default: return current_page;
		}
	}

	function should_show_on_page($el, pageNum) {
		const sp = String($el.data("select-page") || "").toUpperCase();
		const pn = parseInt($el.data("page-number")) || 0;
		switch (sp) {
			case "ALL": return true;
			case "FIRST": return pageNum === 1;
			case "LAST": return pageNum === total_pages;
			case "EVEN": return pageNum % 2 === 0;
			case "ODD": return pageNum % 2 === 1;
			case "SPECIFY": return pageNum === pn;
			default: return true;
		}
	}

	function update_overlay_styles() {
		$wrapper.find(".sig-overlay").each(function () {
			const idx = parseInt($(this).data("sig-index"));
			if (idx === active_sig_index) {
				$(this).css({ "box-shadow": "0 0 0 3px var(--primary)", "z-index": 20, "opacity": 1 });
			} else {
				$(this).css({ "box-shadow": "none", "z-index": 10, "opacity": 0.6 });
			}
		});
	}

	function render_page(pageNum) {
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
					if (!should_show_on_page($el, pageNum)) {
						$el.css("display", "none");
						return;
					}
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
						display: "flex", "align-items": "center", "justify-content": "center",
					});
				});
				update_overlay_styles();
			});

			$pageInfo.text(`Page ${pageNum} / ${total_pages}`);
			$prevBtn.prop("disabled", pageNum <= 1);
			$nextBtn.prop("disabled", pageNum >= total_pages);
		});
	}

	dialog.show();
}

function save_reposition_updates(frm, sigs, sig_updates, callback) {
	let changed = 0;
	for (const [idx, u] of Object.entries(sig_updates)) {
		const s = sigs[parseInt(idx)];
		if (!s) continue;

		const coords_changed = u.coords && u.coords !== (s.customize_coordinates || "");
		const page_changed = u.select_page !== (s.select_page || "");
		const pagenum_changed = String(u.page_number || "") !== String(s.page_number || "");

		if (coords_changed || page_changed || pagenum_changed) {
			frappe.call({
				method: "emsigner.emsigner.api.request_sign.update_coordinates_value",
				args: {
					child_doctype: "emSigner Authorized Signatory",
					child_name: s.name,
					coordinates: u.coords || s.customize_coordinates || "0,0,0,0",
					select_page: u.select_page || s.select_page,
					page_number: u.page_number || "",
				},
				async: false,
			});
			changed++;
		}
	}

	if (changed) {
		frappe.show_alert({ message: __("{0} position(s) updated", [changed]), indicator: "green" }, 3);
	} else {
		frappe.show_alert({ message: __("No changes made"), indicator: "blue" }, 3);
	}
	callback();
}

function open_placement_for_row(frm, row) {
	const config = (frm.doc.print_format || []).find(
		(pf) => pf.permitted_doctype === row.permitted_doctype
	);

	if (!config || !config.sample_document) {
		frappe.show_alert({
			message: __("No sample document configured for {0}. Use 'Setup Doctype' first.", [row.permitted_doctype]),
			indicator: "orange",
		}, 5);
		return;
	}

	const other_signatories = (frm.doc.authorized_signatory || []).filter(
		(s) => s.name !== row.name
			&& s.permitted_doctype === row.permitted_doctype
			&& s.sign_position === "Customize"
			&& s.customize_coordinates
	);

	frappe.call({
		method: "emsigner.emsigner.api.make_sign.download_document_pdf",
		args: {
			doctype: row.permitted_doctype,
			docname: config.sample_document,
			signatory_details: JSON.stringify(row),
			print_format: config.print_format || "",
			letter_head: config.letter_head || "",
		},
		freeze: true,
		freeze_message: __("Loading {0}...", [config.sample_document]),
		callback(r) {
			if (r.message) {
				show_settings_placement_dialog(frm, row, r.message, config, other_signatories);
			} else {
				frappe.show_alert({ message: __("Failed to generate PDF"), indicator: "red" }, 5);
			}
		},
	});
}

const DOCTYPE_COLORS = [
	"var(--blue-50, #EBF5FB)",
	"var(--green-50, #E8F8F5)",
	"var(--orange-50, #FEF5E7)",
	"var(--pink-50, #FDEDEC)",
	"var(--purple-50, #F4ECF7)",
	"var(--cyan-50, #E8F6F3)",
];

function colorize_signatory_rows(frm) {
	if (!frm.fields_dict.authorized_signatory) return;
	const grid = frm.fields_dict.authorized_signatory.grid;
	if (!grid || !grid.grid_rows) return;

	const doctype_color_map = {};
	let color_idx = 0;
	(frm.doc.authorized_signatory || []).forEach((row) => {
		if (row.permitted_doctype && !(row.permitted_doctype in doctype_color_map)) {
			doctype_color_map[row.permitted_doctype] = DOCTYPE_COLORS[color_idx % DOCTYPE_COLORS.length];
			color_idx++;
		}
	});

	setTimeout(() => {
		grid.grid_rows.forEach((grid_row) => {
			if (!grid_row.doc) return;
			const dt = grid_row.doc.permitted_doctype;
			const bg = doctype_color_map[dt];
			if (bg) {
				$(grid_row.row).css("background-color", bg);
			}
		});
	}, 100);
}

function show_settings_placement_dialog(frm, row, pdf_base64, config, other_signatories) {
	let current_page = 1;
	let total_pages = 1;
	let pdf_doc = null;
	let pdf_width = 0;
	let pdf_height = 0;
	let has_dragged = false;
	let signature_coords = { x: 0, y: 0, width: 0, height: 0 };

	if (row.customize_coordinates) {
		const parts = row.customize_coordinates.split(",").map(Number);
		if (parts.length === 4 && parts.every((p) => !isNaN(p))) {
			signature_coords = { x: parts[0], y: parts[1], width: parts[2], height: parts[3] };
			has_dragged = true;
		}
	}

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

	const pf_label = config.print_format ? ` (${config.print_format})` : "";
	const dialog = new frappe.ui.Dialog({
		title: __("Place Signature — {0}{1}", [row.signatory_name || "Signatory", pf_label]),
		size: "extra-large",
		primary_action_label: __("Set Coordinates"),
		primary_action() {
			if (!has_dragged) {
				frappe.show_alert({ message: __("Please drag the signature box to the desired position"), indicator: "orange" }, 5);
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
				frappe.show_alert({ message: __("Signature coordinates saved"), indicator: "green" }, 5);
			});
			dialog.hide();
		},
		secondary_action_label: __("Cancel"),
		secondary_action() { dialog.hide(); },
	});

	dialog.$body.html(`
		<div class="signature-placement-container" style="display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 8px 0;">
			<div style="font-size: 12px; color: var(--text-muted); display: flex; gap: 16px;">
				<span>${__("Document")}: <strong>${frappe.utils.escape_html(config.sample_document)}</strong></span>
				<span>${__("Format")}: <strong>${frappe.utils.escape_html(config.print_format || "Standard")}</strong></span>
			</div>
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
			</div>` : ""}
			<div class="page-controls" style="display: flex; align-items: center; gap: 12px;">
				<button class="btn btn-xs btn-default prev-page" disabled>&laquo; Prev</button>
				<span class="page-info text-muted" style="font-size: 13px;">Page 1 / 1</span>
				<button class="btn btn-xs btn-default next-page" disabled>Next &raquo;</button>
			</div>
			<div class="pdf-viewer-wrapper" style="position: relative; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--fg-color); box-shadow: var(--shadow-sm);">
				<canvas class="pdf-canvas" style="display: block; position: relative; z-index: 1;"></canvas>
				${ghost_overlays}
				<div class="signature-box" style="
					position: absolute; padding: 8px 16px; background: rgba(55, 125, 255, 0.15);
					border: 2px dashed var(--primary); border-radius: 4px; cursor: grab;
					font-size: 13px; font-weight: 500; color: var(--primary);
					user-select: none; z-index: 10; left: 20px; top: 20px;
					display: flex; align-items: center; gap: 6px;
				">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M12 2L12 22M2 12L22 12"/>
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

	load_pdfjs_if_needed().then(() => {
		const pdfData = atob(pdf_base64);
		pdfjsLib.getDocument({ data: pdfData }).promise.then((pdf) => {
			pdf_doc = pdf;
			total_pages = pdf.numPages;
			$pageInfo.text(`Page ${current_page} / ${total_pages}`);
			$prevBtn.prop("disabled", current_page <= 1);
			$nextBtn.prop("disabled", current_page >= total_pages);
			render_page(current_page);
		});
	});

	$prevBtn.on("click", () => { if (current_page > 1) { current_page--; render_page(current_page); } });
	$nextBtn.on("click", () => { if (current_page < total_pages) { current_page++; render_page(current_page); } });

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
				display: "flex", "align-items": "center", "justify-content": "center",
			});
		});
	}

	function render_page(pageNum) {
		pdf_doc.getPage(pageNum).then((page) => {
			const viewport = page.getViewport({ scale: 1.0 });
			const maxWidth = 750;
			const displayScale = Math.min(1, maxWidth / viewport.width);
			const scaledViewport = page.getViewport({ scale: displayScale });

			canvas.width = scaledViewport.width;
			canvas.height = scaledViewport.height;
			pdf_width = scaledViewport.width;
			pdf_height = scaledViewport.height;
			$wrapper.css({ width: scaledViewport.width, height: scaledViewport.height });

			page.render({ canvasContext: canvas.getContext("2d"), viewport: scaledViewport }).promise.then(() => {
				if (signature_coords.x || signature_coords.y) {
					$sigBox.css({ left: signature_coords.x * displayScale, top: pdf_height - signature_coords.y * displayScale });
				}
				position_ghost_overlays(displayScale);
				update_coords_display();
			});

			$pageInfo.text(`Page ${pageNum} / ${total_pages}`);
			$prevBtn.prop("disabled", pageNum <= 1);
			$nextBtn.prop("disabled", pageNum >= total_pages);
			$wrapper.data("displayScale", displayScale);
		});
	}

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

	$(document).on("mousemove.sig_settings", (e) => {
		if (!isDragging) return;
		const rect = $wrapper[0].getBoundingClientRect();
		let x = e.clientX - rect.left - dragOffsetX;
		let y = e.clientY - rect.top - dragOffsetY;
		x = Math.max(0, Math.min(x, pdf_width - $sigBox.outerWidth()));
		y = Math.max(0, Math.min(y, pdf_height - $sigBox.outerHeight()));
		$sigBox.css({ left: x, top: y });

		has_dragged = true;
		const displayScale = $wrapper.data("displayScale") || 1;
		signature_coords = {
			x: x / displayScale,
			y: (pdf_height - y) / displayScale,
			width: $sigBox.outerWidth() / displayScale,
			height: $sigBox.outerHeight() / displayScale,
		};
		update_coords_display();
	});

	$(document).on("mouseup.sig_settings", () => {
		if (isDragging) { isDragging = false; $sigBox.css("cursor", "grab"); }
	});

	function update_coords_display() {
		$coordsDisplay.text(
			`Coordinates: x=${signature_coords.x.toFixed(1)}, y=${signature_coords.y.toFixed(1)}, w=${signature_coords.width.toFixed(1)}, h=${signature_coords.height.toFixed(1)}`
		);
	}

	dialog.onhide = () => {
		$(document).off("mousemove.sig_settings");
		$(document).off("mouseup.sig_settings");
	};

	dialog.show();
}

let _pdfjs_loaded = false;
function load_pdfjs_if_needed() {
	if (_pdfjs_loaded && window.pdfjsLib) return Promise.resolve();
	return new Promise((resolve, reject) => {
		const script = document.createElement("script");
		script.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.min.js";
		script.onload = () => {
			pdfjsLib.GlobalWorkerOptions.workerSrc =
				"https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js";
			_pdfjs_loaded = true;
			resolve();
		};
		script.onerror = () => reject(new Error("Failed to load pdf.js"));
		document.head.appendChild(script);
	});
}
