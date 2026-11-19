import frappe


def execute():
	"""Fill Age (Weeks) on target rows saved before the column existed."""
	target = frappe.qb.DocType("Livestock Performance Target")
	rows = (
		frappe.qb.from_(target)
		.select(target.name, target.age_days)
		.where((target.age_weeks.isnull()) | (target.age_weeks == 0))
		.where(target.age_days > 0)
		.run(as_dict=True)
	)
	for row in rows:
		frappe.db.set_value(
			"Livestock Performance Target",
			row.name,
			"age_weeks",
			round(row.age_days / 7, 2),
			update_modified=False,
		)
