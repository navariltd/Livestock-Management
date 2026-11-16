"""Shared helpers for unit tests (not collected as tests)."""

from unittest.mock import patch

from livestock_management.livestock_management import stock_units


def pin_count_uoms(testcase, uoms=("Nos", "Unit")):
	"""Make Livestock Count UOMs independent of the test site's UOM configuration."""
	patcher = patch.object(stock_units, "get_count_uoms", return_value=list(uoms))
	patcher.start()
	testcase.addCleanup(patcher.stop)
