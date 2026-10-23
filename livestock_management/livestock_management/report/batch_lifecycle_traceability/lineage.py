"""Read-only, conservative inferences from complete Repack stock allocations."""

from collections import defaultdict, deque
from math import isfinite

import frappe
from frappe import _
from frappe.utils import flt

MAX_BATCHES = 200
MAX_DEPTH = 20
TOLERANCE = 0.000001


def classify_repack(allocations, complete, batch_items):
	"""allocations: (batch, warehouse, direction) -> positive count. Never allocate many-to-many."""
	result = dict(
		event_type="Ambiguous transformation",
		parents=[],
		children=[],
		evidence="Not inferred",
		notes="Incomplete, unbalanced, or ambiguous Repack allocations.",
	)
	if not complete or not allocations:
		return result
	incoming, outgoing = defaultdict(float), defaultdict(float)
	for (batch, _warehouse, direction), qty in allocations.items():
		if (
			direction not in ("in", "out")
			or batch not in batch_items
			or not isfinite(qty)
			or qty <= 0
			or abs(qty - round(qty)) > TOLERANCE
		):
			return result
		(incoming if direction == "in" else outgoing)[batch] += qty
	net = {b: incoming.get(b, 0) - outgoing.get(b, 0) for b in incoming.keys() | outgoing.keys()}
	parents = sorted(b for b, qty in net.items() if qty < -TOLERANCE)
	children = sorted(b for b, qty in net.items() if qty > TOLERANCE)
	if not parents and not children:
		return dict(
			event_type="Repack",
			parents=[],
			children=[],
			evidence="Same-batch stock",
			notes="Unchanged batch quantities; no lineage relationship inferred.",
		)
	if (
		not parents
		or not children
		or abs(sum(net.values())) > TOLERANCE
		or (len(parents) > 1 and len(children) > 1)
	):
		return result
	type_ = "Batch replacement"
	if len(parents) == 1 and (len(children) > 1 or parents[0] in incoming):
		type_ = "Split"
	elif len(children) == 1 and (len(parents) > 1 or children[0] in outgoing):
		type_ = "Merge"
	if len({batch_items[b] for b in parents + children}) > 1:
		type_ = "Reclassification / possible grading"
	return dict(
		event_type=type_,
		parents=parents,
		children=children,
		evidence="Inferred from Repack",
		notes="Batch continuity inferred from count-balanced stock movements; not individual-animal ancestry.",
	)


def reachable_batches(root, transformations, include_related=True):
	graph = defaultdict(set)
	for transformation in transformations.values():
		for parent in transformation["parents"]:
			for child in transformation["children"]:
				graph[parent].add(child)
				graph[child].add(parent)
	seen = {root}
	if not include_related:
		return seen
	queue = deque([(root, 0)])
	while queue:
		batch, depth = queue.popleft()
		for other in sorted(graph[batch] - seen):
			if depth >= MAX_DEPTH or len(seen) >= MAX_BATCHES:
				frappe.throw(
					_(
						"Related batch expansion exceeds 200 batches or 20 levels. Disable Include Related Batches to view the selected batch only."
					)
				)
			seen.add(other)
			queue.append((other, depth + 1))
	return seen


def repack_allocations(rows, bundle_rows, eligible_batches, warehouses):
	"""Resolve children of readable Stock Entries only. Ineligible/inaccessible rows invalidate inference."""
	allocations = defaultdict(float)
	if not rows:
		return allocations, False
	for row in rows:
		qty = flt(row.transfer_qty)
		warehouse = row.s_warehouse or row.t_warehouse
		if (
			bool(row.s_warehouse) == bool(row.t_warehouse)
			or warehouse not in warehouses
			or row.stock_uom not in ("Nos", "Unit")
			or not isfinite(qty)
			or qty <= 0
			or abs(qty - round(qty)) > TOLERANCE
		):
			return allocations, False
		direction = "out" if row.s_warehouse else "in"
		parts = (
			bundle_rows.get(row.serial_and_batch_bundle, [])
			if row.serial_and_batch_bundle
			else [frappe._dict(batch_no=row.batch_no, qty=qty)]
		)
		if not parts or abs(sum(abs(flt(p.qty)) for p in parts) - qty) > TOLERANCE:
			return allocations, False
		for part in parts:
			batch = eligible_batches.get(part.batch_no)
			amount = abs(flt(part.qty))
			if (
				not batch
				or batch.item != row.item_code
				or not isfinite(amount)
				or amount <= 0
				or abs(amount - round(amount)) > TOLERANCE
			):
				return allocations, False
			allocations[(part.batch_no, warehouse, direction)] += amount
	return allocations, True


def same_allocations(left, right):
	return left.keys() == right.keys() and all(abs(left[key] - right[key]) <= TOLERANCE for key in left)
