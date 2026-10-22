from unittest import TestCase

import frappe

from livestock_management.livestock_management.performance_targets import age_on, apply_targets


class TestAgeTargets(TestCase):
	def profile(self, rows=None, laying=1):
		return frappe._dict(
			name="Profile",
			all_female_laying_flock=laying,
			targets=rows
			if rows is not None
			else [
				frappe._dict(
					age_days=i, weight_kg=str(1 + i / 10), feed_g="100", fcr="2", egg_yield_percent="80"
				)
				for i in range(10)
			],
			egg_items=[frappe._dict(item="Egg"), frappe._dict(item="Cracked")],
		)

	def apply(self, row=None, profile=None, populations=None, hatch="2026-10-01", intervals=None, eggs=160):
		row = (
			row if row is not None else dict(feed_kg=22, actual_weight=1.3, weight_date="2026-10-03", fcr=2.5)
		)
		notes = []
		apply_targets(
			row,
			frappe._dict(lvm_hatch_date=hatch),
			profile or self.profile(),
			populations if populations is not None else [("2026-10-01", 100), ("2026-10-02", 100)],
			intervals or [],
			eggs,
			notes,
		)
		return row, notes

	def test_age_zero_missing_and_before_hatch(self):
		self.assertEqual(age_on("2026-10-01", "2026-10-01"), 0)
		self.assertIsNone(age_on("2026-09-30", "2026-10-01"))
		self.assertIsNone(age_on("2026-10-01", None))

	def test_weight_uses_measurement_age_and_signed_variance(self):
		row, _ = self.apply()
		self.assertEqual(row["weight_age_days"], 2)
		self.assertEqual(row["target_weight_kg"], 1.2)
		self.assertAlmostEqual(row["weight_variance"], 0.1)
		self.assertAlmostEqual(row["weight_variance_percent"], 100 / 12)

	def test_feed_population_weighting_and_quiet_days(self):
		row, _ = self.apply(populations=[("2026-10-01", 100), ("2026-10-02", 90)])
		self.assertEqual(row["target_feed_kg"], 19)
		self.assertEqual(row["feed_variance"], 3)

	def test_egg_population_weighted_targets_and_percentage_points(self):
		profile = self.profile()
		profile.targets[1].egg_yield_percent = "60"
		row, _ = self.apply(profile=profile, populations=[("2026-10-01", 100), ("2026-10-02", 50)], eggs=120)
		self.assertEqual(row["hen_day_yield"], 80)
		self.assertAlmostEqual(row["target_hen_day_yield"], 11000 / 150)
		self.assertAlmostEqual(row["egg_yield_variance_pp"], 80 - 11000 / 150)

	def test_missing_age_prevents_partial_period_targets(self):
		row, notes = self.apply(
			profile=self.profile(rows=[frappe._dict(age_days=0, feed_g="100", egg_yield_percent="80")])
		)
		self.assertNotIn("target_feed_kg", row)
		self.assertNotIn("target_hen_day_yield", row)
		self.assertTrue(notes)

	def test_zero_targets_are_valid_but_percent_variance_is_undefined(self):
		profile = self.profile()
		for target in profile.targets:
			target.feed_g = "0"
		row, _ = self.apply(profile=profile)
		self.assertEqual(row["target_feed_kg"], 0)
		self.assertEqual(row["feed_variance"], 22)
		self.assertNotIn("feed_variance_percent", row)

	def test_invalid_exposure_or_dates_leave_period_targets_unavailable(self):
		for populations, hatch in [
			([], "2026-10-01"),
			([("2026-10-01", -1)], "2026-10-01"),
			([("2026-10-01", 0)], "2026-10-01"),
			([("2026-10-01", 100)], None),
			([("2026-09-30", 100)], "2026-10-01"),
		]:
			with self.subTest(populations=populations, hatch=hatch):
				row, notes = self.apply(populations=populations, hatch=hatch)
				self.assertNotIn("target_feed_kg", row)
				self.assertTrue(notes)

	def test_non_laying_and_unreadable_eggs_do_not_show_yield(self):
		row, _ = self.apply(profile=self.profile(laying=0))
		self.assertNotIn("hen_day_yield", row)
		row, _ = self.apply(eggs=None)
		self.assertNotIn("hen_day_yield", row)

	def test_fcr_uses_ending_age_and_gain_weighted_targets(self):
		profile = self.profile()
		profile.targets[2].fcr = "3"
		intervals = [dict(to_date="2026-10-02", gain_kg=10), dict(to_date="2026-10-03", gain_kg=30)]
		row, _ = self.apply(profile=profile, intervals=intervals)
		self.assertEqual(row["target_fcr"], 2.75)
		self.assertEqual(row["fcr_variance"], -0.25)
