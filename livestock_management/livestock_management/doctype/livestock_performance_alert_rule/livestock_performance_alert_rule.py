from math import isfinite

import frappe
from frappe import _
from frappe.model.document import Document

ALERT_TYPES = ("Mortality", "Below-target Weight", "Overdue Weighing", "Overdue Treatment")


def scopes_overlap(left, right):
	return all(
		not left.get(key) or not right.get(key) or left.get(key) == right.get(key)
		for key in ("item_code", "warehouse")
	)


def valid_threshold(value, low, high=None, whole=False):
	try:
		number = float(value)
	except (ValueError, TypeError):
		return False
	return (
		isfinite(number)
		and number > low
		and (high is None or number <= high)
		and (not whole or number.is_integer())
	)


class LivestockPerformanceAlertRule(Document):
	def validate(self):
		if self.alert_type not in ALERT_TYPES:
			frappe.throw(_("Select a supported performance alert type."))
		company = frappe.get_doc("Company", self.company)
		company.check_permission("read")
		user = frappe.get_doc("User", self.responsible_user)
		if not user.enabled or user.user_type != "System User":
			frappe.throw(_("Select an enabled System User as the responsible user."))
		if self.item_code:
			item = frappe.get_doc("Item", self.item_code)
			item.check_permission("read")
			if not item.is_stock_item or not item.has_batch_no or item.stock_uom not in ("Nos", "Unit"):
				frappe.throw(_("Select a batch-tracked stock Item counted in Nos or Unit."))
		if self.warehouse:
			house = frappe.get_doc("Warehouse", self.warehouse)
			house.check_permission("read")
			if house.company != self.company or house.is_group:
				frappe.throw(_("Select a non-group warehouse in this Company."))
		if not self.enabled:
			return
		if self.alert_type == "Mortality" and not (
			valid_threshold(self.mortality_percent, 0, 100)
			and valid_threshold(self.minimum_deaths, 0, whole=True)
		):
			frappe.throw(
				_(
					"Set a mortality threshold above zero and at most 100%, and a positive whole minimum death count."
				)
			)
		if self.alert_type == "Below-target Weight" and not valid_threshold(
			self.weight_shortfall_percent, 0, 99.999999
		):
			frappe.throw(_("Weight shortfall must be above zero and below 100%."))
		if self.alert_type == "Overdue Weighing" and not valid_threshold(self.max_gap_days, 0, whole=True):
			frappe.throw(_("Set a positive whole maximum weighing gap."))
		# Serialize rule edits by Company; validation must see rules hidden by User Permissions too.
		frappe.db.get_value("Company", self.company, "name", for_update=True)
		rules = frappe.db.sql(
			"""select name, item_code, warehouse from `tabLivestock Performance Alert Rule`
			where company=%s and alert_type=%s and enabled=1 and name!=%s for update""",
			(self.company, self.alert_type, self.name or ""),
			as_dict=True,
		)
		if any(scopes_overlap(self, other) for other in rules):
			frappe.throw(
				_("Enabled rules for this Company and alert type must not overlap Item/House scope.")
			)
