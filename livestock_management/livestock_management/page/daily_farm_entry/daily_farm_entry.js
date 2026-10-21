// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.pages["daily-farm-entry"].on_page_load = function (wrapper) {
	new DailyFarmEntry(wrapper);
};

class DailyFarmEntry {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Daily Farm Entry"),
			single_column: true,
		});
		this.api = "livestock_management.livestock_management.daily_farm_entry.";
		this.root = $('<div class="daily-farm-entry"></div>').appendTo(this.page.main);
		this.root.append(
			$('<p class="text-muted"></p>').text(
				__(
					"Record today's work. Stock entries save as drafts for review; weights and observations save immediately."
				)
			)
		);
		const context = $('<div class="farm-context"></div>').appendTo(this.root);
		this.context = new frappe.ui.FieldGroup({ body: context, fields: this.context_fields() });
		this.context.make();
		this.cards = $('<div class="farm-activities"></div>').appendTo(this.root);
		this.history = $('<div class="farm-history"></div>').appendTo(this.root);
		this.page.add_inner_button(__("Refresh activity history"), () => this.refresh_history());
		this.make_cards();
	}

	context_fields() {
		return [
			{ fieldtype: "Section Break", label: __("Farm and flock") },
			{
				fieldname: "company",
				fieldtype: "Link",
				options: "Company",
				label: __("Company"),
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
				change: () => this.clear(["house", "project", "employee"]),
			},
			{
				fieldname: "item",
				fieldtype: "Link",
				options: "Item",
				label: __("Livestock Item"),
				reqd: 1,
				get_query: () => ({
					filters: { is_stock_item: 1, has_batch_no: 1, has_serial_no: 0, disabled: 0 },
				}),
				change: () => this.clear(["batch"]),
			},
			{
				fieldname: "batch",
				fieldtype: "Link",
				options: "Batch",
				label: __("Livestock Batch"),
				reqd: 1,
				get_query: () => ({ filters: { item: this.value("item"), disabled: 0 } }),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "house",
				fieldtype: "Link",
				options: "Warehouse",
				label: __("Livestock house"),
				reqd: 1,
				get_query: () => this.warehouse_query(),
			},
			{
				fieldname: "posting_datetime",
				fieldtype: "Datetime",
				label: __("Activity date and time"),
				reqd: 1,
				default: frappe.datetime.now_datetime(),
			},
			{
				fieldname: "project",
				fieldtype: "Link",
				options: "Project",
				label: __("Production cycle / Project"),
				get_query: () => ({ filters: { company: this.value("company") } }),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "employee",
				fieldtype: "Link",
				options: "Employee",
				label: __("Performed by"),
				reqd: 1,
				get_query: () => ({
					filters: { company: this.value("company"), status: "Active" },
				}),
			},
			{ fieldname: "shift", fieldtype: "Link", options: "Shift Type", label: __("Shift") },
		];
	}

	value(name) {
		return this.context?.fields_dict[name]?.get_value();
	}
	clear(names) {
		for (const name of names) this.context?.fields_dict[name]?.set_value("");
	}
	warehouse_query(company = this.value("company")) {
		return { filters: { company, is_group: 0, disabled: 0 } };
	}

	async make_cards() {
		const activities = [
			["feeding", "Feeding", "Issue feed from its store to this flock.", "Stock Entry"],
			["mortality", "Mortality", "Record deaths with a reason and quantity.", "Stock Entry"],
			[
				"weighing",
				"Weighing",
				"Record a sample's average weight in Kg per animal.",
				"Weight Record",
			],
			[
				"produce",
				"Produce collection",
				"Receive produce into its store, separately from the flock.",
				"Stock Entry",
			],
			[
				"observation",
				"Observation",
				"Record a husbandry activity or observation.",
				"Livestock Event",
			],
		];
		for (const [activity, title, description, doctype] of activities) {
			await frappe.model.with_doctype(doctype);
			const card = $('<section class="farm-activity"></section>').appendTo(this.cards);
			$("<h4></h4>").text(__(title)).appendTo(card);
			$('<p class="text-muted"></p>').text(__(description)).appendTo(card);
			const allowed = frappe.model.can_create(doctype);
			$('<button class="btn btn-default btn-sm" type="button"></button>')
				.text(allowed ? __("Add {0}", [__(title)]) : __("Create permission required"))
				.prop("disabled", !allowed)
				.on("click", () => this.open_activity(activity, __(title)))
				.appendTo(card);
		}
		this.history.append(
			$('<p class="farm-empty text-muted"></p>').text(
				__("Select a Company and Batch, then refresh to see recent entries created here.")
			)
		);
	}

	open_activity(activity, title) {
		const context = this.context.get_values();
		if (!context) return;
		const bytes = crypto.getRandomValues(new Uint8Array(16));
		bytes[6] = (bytes[6] & 15) | 64;
		bytes[8] = (bytes[8] & 63) | 128;
		const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
		const operation_id = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(
			12,
			16
		)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
		const fields = this.activity_fields(activity, context);
		let saving = false;
		let dirty = true;
		const dialog = new frappe.ui.Dialog({
			title,
			size: ["feeding", "produce"].includes(activity) ? "extra-large" : "large",
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="text-muted">${frappe.utils.escape_html(
						__("{0} · {1} · {2}", [
							context.batch,
							context.house,
							context.posting_datetime,
						])
					)}</p>`,
				},
				...fields,
			],
			primary_action_label: ["weighing", "observation"].includes(activity)
				? __("Save record")
				: __("Save draft"),
			primary_action: async (values) => {
				if (saving) return;
				saving = true;
				dialog.get_primary_btn().prop("disabled", true);
				const payload_values = { ...values };
				if (values.items)
					payload_values.items = values.items.map((row) => ({
						item: row.item,
						quantity: row.quantity,
						warehouse: row.warehouse,
						batch: row.batch || null,
						...(activity === "produce" ? { rate: row.rate } : {}),
					}));
				try {
					const response = await frappe.call({
						method: this.api + "save_activity",
						args: {
							payload: JSON.stringify({
								activity,
								operation_id,
								context,
								values: payload_values,
							}),
						},
					});
					dirty = false;
					saving = false;
					dialog.hide();
					this.show_saved(response.message);
					frappe.show_alert({ message: __("Activity saved"), indicator: "green" });
				} finally {
					saving = false;
					dialog.get_primary_btn().prop("disabled", false);
				}
			},
		});
		// Retain the same dialog and operation ID after errors, including a lost response.
		dialog.$wrapper.on("hide.bs.modal", (event) => {
			if (
				saving ||
				(dirty && !window.confirm(__("Close this activity? Unsaved values will be lost.")))
			) {
				event.preventDefault();
			}
		});
		dialog.show();
		if (activity === "feeding" || activity === "produce") {
			dialog.fields_dict.items.grid.update_docfield_property(
				"item",
				"onchange",
				function () {
					const row = this.doc;
					if (!row) return;
					row.batch = null;
					row.stock_uom = "";
					if (!row.item) {
						dialog.fields_dict.items.grid.refresh();
						return;
					}
					const item = row.item;
					frappe.db.get_value("Item", item, "stock_uom").then((response) => {
						if (row.item !== item) return;
						row.stock_uom = response.message.stock_uom;
						dialog.fields_dict.items.grid.refresh();
					});
				}
			);
		}
	}

	activity_fields(activity, context) {
		if (activity === "feeding" || activity === "produce") {
			return [
				{
					fieldtype: "HTML",
					options: `<p>${frappe.utils.escape_html(
						__(
							"Quantities use each Item's stock UOM. Select the feed/produce inventory Batch, not the livestock Batch. Serial-tracked items require the standard form."
						)
					)}</p>`,
				},
				{
					fieldname: "items",
					label: __("Items"),
					fieldtype: "Table",
					reqd: 1,
					in_place_edit: true,
					data: [{}],
					fields: [
						{
							fieldname: "item",
							label: __("Item"),
							fieldtype: "Link",
							options: "Item",
							reqd: 1,
							in_list_view: 1,
							get_query: () => ({
								filters: { is_stock_item: 1, has_serial_no: 0, disabled: 0 },
							}),
						},
						{
							fieldname: "quantity",
							label: __("Quantity"),
							fieldtype: "Float",
							reqd: 1,
							in_list_view: 1,
						},
						{
							fieldname: "stock_uom",
							label: __("Stock UOM"),
							fieldtype: "Data",
							read_only: 1,
							in_list_view: 1,
						},
						{
							fieldname: "warehouse",
							label:
								activity === "feeding" ? __("Feed store") : __("Receiving store"),
							fieldtype: "Link",
							options: "Warehouse",
							reqd: 1,
							in_list_view: 1,
							get_query: () => this.warehouse_query(context.company),
						},
						{
							fieldname: "batch",
							label: __("Inventory Batch"),
							fieldtype: "Link",
							options: "Batch",
							get_query: (row) => ({ filters: { item: row.item, disabled: 0 } }),
						},
						...(activity === "produce"
							? [
									{
										fieldname: "rate",
										label: __("Rate per stock unit (Company currency)"),
										fieldtype: "Currency",
										reqd: 1,
										in_list_view: 1,
									},
							  ]
							: []),
					],
				},
			];
		}
		if (activity === "mortality")
			return [
				{
					fieldname: "quantity",
					label: __("Number of deaths"),
					fieldtype: "Int",
					reqd: 1,
				},
				{
					fieldname: "reason",
					label: __("Mortality reason"),
					fieldtype: "Link",
					options: "Mortality Reason",
					reqd: 1,
				},
			];
		if (activity === "weighing")
			return [
				{
					fieldname: "sample_size",
					label: __("Animals sampled"),
					fieldtype: "Int",
					reqd: 1,
				},
				{
					fieldname: "average_weight",
					label: __("Average weight per animal (Kg)"),
					fieldtype: "Float",
					reqd: 1,
				},
			];
		return [
			{
				fieldname: "husbandry",
				label: __("Husbandry practice"),
				fieldtype: "Link",
				options: "Husbandry Practice",
				reqd: 1,
				get_query: () => ({ filters: { name: ["!=", "Pregnancy Check"] } }),
			},
			{
				fieldname: "ends_on",
				label: __("Ends on"),
				fieldtype: "Datetime",
				default: context.posting_datetime,
			},
			{ fieldname: "notes", label: __("Notes"), fieldtype: "Small Text" },
		];
	}

	show_saved(record) {
		this.history.find(".farm-empty").remove();
		const line = $('<div class="farm-saved"></div>').prependTo(this.history);
		$("<a></a>")
			.text(`${record.doctype}: ${record.name}`)
			.attr("href", frappe.utils.get_form_link(record.doctype, record.name))
			.appendTo(line);
		const state =
			record.status ||
			(record.docstatus === 1
				? __("Submitted")
				: record.docstatus === 2
				? __("Cancelled")
				: record.doctype === "Stock Entry"
				? __("Draft — open to review")
				: __("Saved"));
		$('<span class="text-muted"></span>').text(` · ${state}`).appendTo(line);
	}

	async refresh_history() {
		const company = this.value("company"),
			batch = this.value("batch");
		if (!company || !batch) {
			frappe.msgprint(__("Select Company and Batch first."));
			return;
		}
		const response = await frappe.call({
			method: this.api + "get_recent_activities",
			args: { company, batch },
		});
		if (company !== this.value("company") || batch !== this.value("batch")) return;
		this.history.empty().append($("<h4></h4>").text(__("Recent farm entries")));
		if (!response.message.length)
			this.history.append(
				$('<p class="farm-empty text-muted"></p>').text(
					__("No recent entries for this Company and Batch.")
				)
			);
		for (const record of response.message.slice().reverse()) this.show_saved(record);
	}
}
