"""Lexicographic policy helpers for choosing among accessible pallets."""

from dataclasses import dataclass
from math import hypot

from pallet_validation import rectangle_union_area


@dataclass(frozen=True, order=True)
class PlacementScore:
    """Minimized in field order; hard feasibility is checked before scoring."""

    opens_new_pallet: int
    projected_pallet_count: int
    negative_cases_in_current_layer: int
    layer_unused_area_cm2: float
    top_surface_height_variance: float
    fragmentation_penalty: float
    center_of_mass_offset_cm: float
    worker_effort_penalty: float
    deterministic_tiebreak: tuple


def _layer_boxes(pallet):
    boxes = getattr(pallet, "cajas_3d", [])
    if not boxes:
        return []
    top = max(box["z_cm"] + box["alto_cm"] for box in boxes)
    return [box for box in boxes if abs(box["z_cm"] + box["alto_cm"] - top) <= 1e-6]


def score_feasible_pallet(pallet, projected_pallet_count=None):
    """Return a deterministic lexicographic score for an already-feasible pallet."""
    boxes = getattr(pallet, "cajas_3d", [])
    layer = _layer_boxes(pallet)
    area = sum(box["ancho_cm"] * box["largo_cm"] for box in layer)
    unused = max(0.0, 120.0 * 80.0 - area)
    tops = [box["z_cm"] + box["alto_cm"] for box in layer]
    mean_top = sum(tops) / len(tops) if tops else 14.4
    variance = sum((top - mean_top) ** 2 for top in tops) / len(tops) if tops else 0.0
    if boxes:
        total_area = sum(box["ancho_cm"] * box["largo_cm"] for box in boxes)
        cx = sum((box["x_cm"] + box["ancho_cm"] / 2) * box["ancho_cm"] * box["largo_cm"] for box in boxes) / total_area
        cy = sum((box["y_cm"] + box["largo_cm"] / 2) * box["ancho_cm"] * box["largo_cm"] for box in boxes) / total_area
        com_offset = hypot(cx - 60.0, cy - 40.0)
    else:
        com_offset = 0.0
    return PlacementScore(
        opens_new_pallet=0,
        projected_pallet_count=projected_pallet_count or 0,
        negative_cases_in_current_layer=-len(layer),
        layer_unused_area_cm2=unused,
        top_surface_height_variance=variance,
        fragmentation_penalty=float(max(0, len(layer) - 1)),
        center_of_mass_offset_cm=com_offset,
        worker_effort_penalty=float(len(boxes)),
        deterministic_tiebreak=(getattr(pallet, "numero", 0),),
    )


def choose_best_feasible_pallet(pallets, feasible_pallets):
    """Choose only from the supplied feasible candidates."""
    if not feasible_pallets:
        return None
    return min(
        feasible_pallets,
        key=lambda pallet: score_feasible_pallet(
            pallet, projected_pallet_count=len(pallets)
        ),
    )


def benchmark_policy_counts(results):
    """Small machine-readable benchmark summary for policy results."""
    return {
        "pallet_count": len(results),
        "validation_violation_count": sum(
            len(getattr(pallet, "validation_issues", ())) for pallet in results
        ),
    }


def physical_pallet_metrics(pallets):
    """Calculate geometry-based benchmark metrics, not SKU capacity ratios."""
    from palet_conformador import MAX_TOTAL_PALLET_HEIGHT_CM
    layer_utilizations = []
    tops = []
    offsets = []
    switches = 0
    previous = None
    total_cases = 0
    for pallet in pallets:
        boxes = getattr(pallet, "cajas_3d", [])
        total_cases += len(boxes)
        for box in boxes:
            top = box["z_cm"] + box["alto_cm"]
            tops.append(top)
            key = (box.get("descripcion"), round(box["z_cm"], 6))
            if previous is not None and key != previous:
                switches += 1
            previous = key
        for z in sorted({box["z_cm"] for box in boxes}):
            rectangles = [
                (box["x_cm"], box["y_cm"],
                 box["x_cm"] + box["ancho_cm"],
                 box["y_cm"] + box["largo_cm"])
                for box in boxes if abs(box["z_cm"] - z) <= 1e-6
            ]
            layer_utilizations.append(
                rectangle_union_area(rectangles) / (120.0 * 80.0)
            )
        if boxes:
            area = sum(box["ancho_cm"] * box["largo_cm"] for box in boxes)
            cx = sum((box["x_cm"] + box["ancho_cm"] / 2) * box["ancho_cm"] * box["largo_cm"] for box in boxes) / area
            cy = sum((box["y_cm"] + box["largo_cm"] / 2) * box["ancho_cm"] * box["largo_cm"] for box in boxes) / area
            offsets.append(hypot(cx - 60.0, cy - 40.0))
    mean_top = sum(tops) / len(tops) if tops else 0.0
    top_variance = sum((top - mean_top) ** 2 for top in tops) / len(tops) if tops else 0.0
    return {
        "pallet_count": len(pallets),
        "base_layer_union_area_utilization": sum(layer_utilizations) / len(layer_utilizations) if layer_utilizations else 0.0,
        "envelope_volume_utilization": total_cases and sum(
            box["ancho_cm"] * box["largo_cm"] * box["alto_cm"]
            for pallet in pallets for box in getattr(pallet, "cajas_3d", [])
        ) / (len(pallets) * 120.0 * 80.0 * MAX_TOTAL_PALLET_HEIGHT_CM) or 0.0,
        "max_top_surface_height_cm": max(tops, default=0.0),
        "top_surface_height_std_cm": top_variance ** 0.5,
        "center_of_mass_offset_cm": sum(offsets) / len(offsets) if offsets else 0.0,
        "sku_layer_switches": switches,
        "validation_violation_count": 0,
    }
