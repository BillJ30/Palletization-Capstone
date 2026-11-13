"""Validated, SKU-specific promotion capacity calculations."""

from dataclasses import dataclass, replace
from copy import deepcopy
from math import isfinite

from palet_conformador import (
    MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
    MAX_TOTAL_PALLET_HEIGHT_CM,
    PALLET_BASE_HEIGHT_CM,
    procesar_pedido_dict,
)
from pallet_validation import validate_order_geometry


@dataclass(frozen=True)
class AddOnCapacityResult:
    article: int
    additional_cases_without_new_pallet: int
    baseline_pallet_count: int
    resulting_pallet_count: int
    limiting_constraint: str | None
    remaining_weight_kg: float
    remaining_height_cm: float
    policy: str


def _order_parts(order):
    if isinstance(order, dict):
        return str(order.get("pedido_id", "ADD_ON")), list(order["lineas"])
    if isinstance(order, tuple) and len(order) == 2:
        return str(order[0]), list(order[1])
    return "ADD_ON", list(order)


def _trial_result(order_id, lines, policy):
    result = procesar_pedido_dict(
        order_id, deepcopy(lines),
        MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
        usar_3d=True,
        operational_policy=policy,
    )
    config = {
        "PALET_ANCHO_CM": 120.0,
        "PALET_LARGO_CM": 80.0,
        "PALLET_BASE_HEIGHT_CM": PALLET_BASE_HEIGHT_CM,
        "MAX_TOTAL_PALLET_HEIGHT_CM": MAX_TOTAL_PALLET_HEIGHT_CM,
        "MIN_SUPPORT_RATIO": 1.0,
        "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
        "PALLET_TARE_WEIGHT_KG": 0.0,
    }
    validation = validate_order_geometry(result["palets_picking"], config)
    return result, validation


def _constraint(result, validation):
    if result is None:
        return "hard_constraint"
    if not validation.valid:
        codes = {issue.code for issue in validation.issues}
        for code, label in (
            ("OVERWEIGHT", "weight"), ("HEIGHT_EXCEEDED", "height"),
            ("OUT_OF_BOUNDS", "geometry"), ("OVERLAP", "collision"),
            ("UNDER_SUPPORTED", "support"), ("STATION_ORDER", "route"),
        ):
            if code in codes:
                return label
        return "hard_constraint"
    return None


def additional_cases(order, candidate_sku, policy="single_active", upper_bound=None):
    """Return the largest validated integer add-on without extra pallets.

    This is a heuristic capacity because each trial reruns the deterministic
    route-aware packer, rather than solving a global mathematical optimum.
    """
    if policy not in {"single_active", "multiple_open"}:
        raise ValueError("policy must be 'single_active' or 'multiple_open'")
    order_id, original_lines = _order_parts(order)
    if not hasattr(candidate_sku, "cajas_linea"):
        raise TypeError("candidate_sku must be a validated LineaPedido")
    if candidate_sku.station_index is None or not candidate_sku.tiene_dimensiones:
        return AddOnCapacityResult(
            int(candidate_sku.articulo), 0, 0, 0, "route_or_geometry", 0.0, 0.0, policy
        )
    baseline, baseline_validation = _trial_result(order_id, original_lines, policy)
    if not baseline_validation.valid:
        raise ValueError("cannot calculate add-on capacity for an invalid baseline order")
    baseline_count = int(baseline["n_picking_fisico"] + baseline["palets_completos"] + baseline["n_semipalet"])
    cache = {0: (baseline, baseline_validation)}

    def trial(quantity):
        if quantity not in cache:
            candidate = replace(candidate_sku, cajas_linea=quantity)
            try:
                cache[quantity] = _trial_result(order_id, original_lines + [candidate], policy)
            except (ValueError, RuntimeError):
                cache[quantity] = (None, None)
        return cache[quantity]

    def fits(quantity):
        result, validation = trial(quantity)
        return (
            result is not None and validation is not None and validation.valid
            and int(result["n_picking_fisico"] + result["palets_completos"] + result["n_semipalet"]) <= baseline_count
        )

    if upper_bound is None:
        upper_bound = 1
        while upper_bound < 10000 and fits(upper_bound):
            upper_bound *= 2
        upper_bound = min(upper_bound, 10000)
    upper_bound = max(0, int(upper_bound))
    if upper_bound == 0 or not fits(1):
        best = 0
    else:
        low, high = 1, upper_bound
        while low < high:
            middle = (low + high + 1) // 2
            if fits(middle):
                low = middle
            else:
                high = middle - 1
        best = low
        # Confirm the boundary and its immediate neighbours against cached trials.
        fits(best)
        if best < upper_bound:
            fits(best + 1)
    result, validation = trial(best)
    if result is None:
        result, validation = baseline, baseline_validation
    gross = validation.gross_weight_kg or 0.0
    remaining_weight = max(0.0, MAX_MIXED_PALLET_GROSS_WEIGHT_KG - gross)
    max_top = max(
        (box["z_cm"] + box["alto_cm"] for pallet in result["palets_picking"] for box in pallet["cajas_3d"]),
        default=PALLET_BASE_HEIGHT_CM,
    )
    remaining_height = max(0.0, MAX_TOTAL_PALLET_HEIGHT_CM - max_top)
    limiting = None if best > 0 else _constraint(*trial(1))
    return AddOnCapacityResult(
        int(candidate_sku.articulo), best, baseline_count,
        int(result["n_picking_fisico"] + result["palets_completos"] + result["n_semipalet"]),
        limiting, remaining_weight, remaining_height, policy,
    )


def format_add_on_capacity(result):
    binding = result.limiting_constraint or "none"
    return (
        f"SKU {result.article}: up to {result.additional_cases_without_new_pallet} "
        f"additional cases with no new pallet\n"
        f"Binding limit: {binding}\n"
        f"Baseline/result: {result.baseline_pallet_count} pallets / "
        f"{result.resulting_pallet_count} pallets"
    )
