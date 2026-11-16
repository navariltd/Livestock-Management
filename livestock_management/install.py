from livestock_management.patches.add_livestock_count_uom import execute as add_livestock_count_uom


def after_install():
	# Patches are marked complete, not run, on a fresh install.
	add_livestock_count_uom()
