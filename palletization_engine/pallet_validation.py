"""Independent geometry validation for exported pallet placements."""

from dataclasses import dataclass
import math


EPS_CM = 1e-6
REQUIRED_FIELDS = ("x_cm", "y_cm", "z_cm", "ancho_cm", "largo_cm", "alto_cm")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    pallet_number: int
    case_indices: tuple[int, ...]
    message: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: tuple[ValidationIssue, ...]
    diagnostics: tuple[str, ...] = ()
    gross_weight_kg: float | None = None


@dataclass(frozen=True)
class SupportResult:
    supported: bool
    base_z_cm: float
    support_ratio: float
    contact_area_cm2: float


class InvalidPalletGeometryError(ValueError):
    """Raised when an order contains placements that cannot be exported."""

    def __init__(self, result: ValidationResult):
        self.result = result
        summary = "; ".join(issue.message for issue in result.issues[:5])
        if len(result.issues) > 5:
            summary += f"; ... ({len(result.issues)} issues total)"
        super().__init__(f"Invalid pallet geometry: {summary}")


def intervals_overlap_positive(a0, a1, b0, b1, eps=EPS_CM):
    return min(a1, b1) - max(a0, b0) > eps


def cuboids_overlap(a: dict, b: dict, eps=EPS_CM) -> bool:
    return (
        intervals_overlap_positive(a["x_cm"], a["x_cm"] + a["ancho_cm"],
                                   b["x_cm"], b["x_cm"] + b["ancho_cm"], eps)
        and intervals_overlap_positive(a["y_cm"], a["y_cm"] + a["largo_cm"],
                                       b["y_cm"], b["y_cm"] + b["largo_cm"], eps)
        and intervals_overlap_positive(a["z_cm"], a["z_cm"] + a["alto_cm"],
                                       b["z_cm"], b["z_cm"] + b["alto_cm"], eps)
    )


def rectangle_union_area(rectangles, eps=EPS_CM):
    """Return the exact union area of (x0, y0, x1, y1) rectangles."""
    clipped = [r for r in rectangles if r[2] - r[0] > eps and r[3] - r[1] > eps]
    if not clipped:
        return 0.0

    x_edges = sorted({edge for rectangle in clipped for edge in (rectangle[0], rectangle[2])})
    area = 0.0
    for x0, x1 in zip(x_edges, x_edges[1:]):
        if x1 - x0 <= eps:
            continue
        y_intervals = [
            (rectangle[1], rectangle[3])
            for rectangle in clipped
            if rectangle[0] < x1 - eps and rectangle[2] > x0 + eps
        ]
        y_intervals.sort()
        covered_y = 0.0
        current_start = current_end = None
        for y0, y1 in y_intervals:
            if current_start is None:
                current_start, current_end = y0, y1
            elif y0 <= current_end + eps:
                current_end = max(current_end, y1)
            else:
                covered_y += current_end - current_start
                current_start, current_end = y0, y1
        if current_start is not None:
            covered_y += current_end - current_start
        area += (x1 - x0) * covered_y
    return area


def exact_support_result(
    x0_cm: float,
    y0_cm: float,
    ancho_cm: float,
    largo_cm: float,
    base_z_cm: float,
    placed: list[dict],
    config,
) -> SupportResult:
    """Measure support from exact case top surfaces at one rigid base plane."""
    max_x = float(_get_config(config, "PALET_ANCHO_CM", 120.0))
    max_y = float(_get_config(config, "PALET_LARGO_CM", 80.0))
    deck_z = float(_get_config(config, "PALLET_BASE_HEIGHT_CM", 14.4))
    min_ratio = float(_get_config(config, "MIN_SUPPORT_RATIO", 1.0))
    base_area = ancho_cm * largo_cm

    inside = (
        x0_cm >= -EPS_CM and y0_cm >= -EPS_CM
        and x0_cm + ancho_cm <= max_x + EPS_CM
        and y0_cm + largo_cm <= max_y + EPS_CM
    )
    if base_area <= 0 or not inside:
        return SupportResult(False, base_z_cm, 0.0, 0.0)
    if abs(base_z_cm - deck_z) <= EPS_CM:
        return SupportResult(True, base_z_cm, 1.0, base_area)

    contact_rectangles = []
    for box in placed:
        top_z = box["z_cm"] + box["alto_cm"]
        if abs(top_z - base_z_cm) > EPS_CM:
            continue
        contact_rectangles.append((
            max(x0_cm, box["x_cm"]),
            max(y0_cm, box["y_cm"]),
            min(x0_cm + ancho_cm, box["x_cm"] + box["ancho_cm"]),
            min(y0_cm + largo_cm, box["y_cm"] + box["largo_cm"]),
        ))

    contact_area = rectangle_union_area(contact_rectangles)
    ratio = contact_area / base_area
    return SupportResult(ratio + EPS_CM >= min_ratio, base_z_cm, ratio, contact_area)


def _get_config(config, name, default=None):
    aliases = {
        "PALLET_BASE_HEIGHT_CM": "MADERA_CM",
        "MAX_TOTAL_PALLET_HEIGHT_CM": "ALTURA_MAX_CM",
    }
    if isinstance(config, dict):
        value = config.get(name)
        if value is None and name in aliases:
            value = config.get(aliases[name])
        return default if value is None else value
    value = getattr(config, name, None)
    if value is None and name in aliases:
        value = getattr(config, aliases[name], None)
    return default if value is None else value


def _boxes(pallet):
    if isinstance(pallet, dict):
        return pallet.get("cajas_3d", [])
    return getattr(pallet, "cajas_3d", [])


def _pallet_number(pallet, fallback):
    if isinstance(pallet, dict):
        return pallet.get("numero", fallback)
    return getattr(pallet, "numero", fallback)


def _case_label(box, index):
    return str(box.get("descripcion", box.get("id", f"case[{index}]")))


def _station_order_issues(pallet_number, valid_boxes):
    issues = []
    for index, box in valid_boxes:
        if "station_index" not in box or box["station_index"] is None:
            issues.append(ValidationIssue(
                "MISSING_STATION_MAPPING", pallet_number, (index,),
                f"pallet {pallet_number}, case {index} ({_case_label(box, index)}), "
                f"coordinates {box}: missing station_index",
            ))

    for lower_index, lower in valid_boxes:
        if lower.get("station_index") is None:
            continue
        lower_top = lower["z_cm"] + lower["alto_cm"]
        for upper_index, upper in valid_boxes:
            if lower_index == upper_index or upper.get("station_index") is None:
                continue
            same_footprint = (
                intervals_overlap_positive(
                    lower["x_cm"], lower["x_cm"] + lower["ancho_cm"],
                    upper["x_cm"], upper["x_cm"] + upper["ancho_cm"],
                )
                and intervals_overlap_positive(
                    lower["y_cm"], lower["y_cm"] + lower["largo_cm"],
                    upper["y_cm"], upper["y_cm"] + upper["largo_cm"],
                )
            )
            if same_footprint and upper["z_cm"] >= lower_top - EPS_CM and upper["z_cm"] > lower["z_cm"] + EPS_CM:
                if upper["station_index"] < lower["station_index"]:
                    issues.append(ValidationIssue(
                        "STATION_ORDER_VIOLATION", pallet_number,
                        (lower_index, upper_index),
                        f"pallet {pallet_number}, case {upper_index} station "
                        f"{upper['station_index']} is above case {lower_index} station "
                        f"{lower['station_index']}: lower coordinates {lower}, "
                        f"upper coordinates {upper}",
                    ))
    return issues


def _load_bearing_assessment(pallet_number, valid_boxes):
    upper_cases = []
    for upper_index, upper in valid_boxes:
        for lower_index, lower in valid_boxes:
            if upper_index == lower_index:
                continue
            if abs((lower["z_cm"] + lower["alto_cm"]) - upper["z_cm"]) > EPS_CM:
                continue
            if (
                intervals_overlap_positive(lower["x_cm"], lower["x_cm"] + lower["ancho_cm"], upper["x_cm"], upper["x_cm"] + upper["ancho_cm"])
                and intervals_overlap_positive(lower["y_cm"], lower["y_cm"] + lower["largo_cm"], upper["y_cm"], upper["y_cm"] + upper["largo_cm"])
            ):
                upper_cases.append((lower_index, lower, upper_index, upper))

    if not upper_cases:
        return [], ()

    diagnostics = []
    if not any(lower.get("max_load_above_kg") is not None for _, lower, _, _ in upper_cases):
        return [], ("load_data_unavailable",)

    issues = []
    load_by_lower = {}
    for lower_index, lower, upper_index, upper in upper_cases:
        max_load = lower.get("max_load_above_kg")
        if max_load is None:
            diagnostics.append("load_data_unavailable")
            continue
        load_by_lower.setdefault((lower_index, max_load), 0.0)
        try:
            upper_weight = float(upper.get("peso_caja"))
        except (TypeError, ValueError):
            upper_weight = 0.0
        load_by_lower[(lower_index, max_load)] += upper_weight
    for (lower_index, max_load), assigned_load in load_by_lower.items():
        if assigned_load > max_load + EPS_CM:
            issues.append(ValidationIssue(
                "LOAD_BEARING_EXCEEDED", pallet_number, (lower_index,),
                f"pallet {pallet_number}, case {lower_index}: conservatively assigned "
                f"load above={assigned_load:.3f} kg exceeds max_load_above_kg="
                f"{max_load:.3f} kg",
            ))
    return issues, tuple(sorted(set(diagnostics)))


def validate_pallet_geometry(pallet, config) -> ValidationResult:
    pallet_number = _pallet_number(pallet, 0)
    max_x = float(_get_config(config, "PALET_ANCHO_CM", 120.0))
    max_y = float(_get_config(config, "PALET_LARGO_CM", 80.0))
    base_z = float(_get_config(config, "PALLET_BASE_HEIGHT_CM", 14.4))
    max_z = float(_get_config(config, "MAX_TOTAL_PALLET_HEIGHT_CM", 180.0))
    issues = []
    valid_boxes = []
    cargo_weight_kg = 0.0

    for index, box in enumerate(_boxes(pallet)):
        missing = [field for field in REQUIRED_FIELDS if field not in box]
        if missing:
            issues.append(ValidationIssue(
                "MISSING_FIELD", pallet_number, (index,),
                f"pallet {pallet_number}, case {index} ({_case_label(box, index)}), "
                f"coordinates/dimensions {box}: missing {', '.join(missing)}",
            ))
            continue

        values = {}
        invalid_numeric = []
        for field in REQUIRED_FIELDS:
            if isinstance(box[field], bool):
                invalid_numeric.append(field)
                continue
            try:
                value = float(box[field])
            except (TypeError, ValueError):
                invalid_numeric.append(field)
                continue
            if not math.isfinite(value):
                invalid_numeric.append(field)
            else:
                values[field] = value
        if invalid_numeric:
            issues.append(ValidationIssue(
                "NON_FINITE_NUMERIC", pallet_number, (index,),
                f"pallet {pallet_number}, case {index} ({_case_label(box, index)}), "
                f"coordinates/dimensions {box}: non-finite or non-numeric "
                f"{', '.join(invalid_numeric)}",
            ))
            continue

        coordinates = (
            f"x={values['x_cm']}, y={values['y_cm']}, z={values['z_cm']}, "
            f"w={values['ancho_cm']}, d={values['largo_cm']}, h={values['alto_cm']}"
        )
        if any(values[field] <= 0 for field in ("ancho_cm", "largo_cm", "alto_cm")):
            issues.append(ValidationIssue(
                "NON_POSITIVE_DIMENSION", pallet_number, (index,),
                f"pallet {pallet_number}, case {index} ({_case_label(box, index)}), "
                f"{coordinates}: dimensions must be strictly positive",
            ))
            continue

        x1 = values["x_cm"] + values["ancho_cm"]
        y1 = values["y_cm"] + values["largo_cm"]
        z1 = values["z_cm"] + values["alto_cm"]
        if values["x_cm"] < 0.0 or x1 > max_x or values["y_cm"] < 0.0 or y1 > max_y or values["z_cm"] < base_z:
            issues.append(ValidationIssue(
                "OUT_OF_BOUNDS", pallet_number, (index,),
                f"pallet {pallet_number}, case {index} ({_case_label(box, index)}), "
                f"{coordinates}: bounds must be x in [0, {max_x}], "
                f"y in [0, {max_y}], z >= {base_z}",
            ))
        elif z1 > max_z:
            issues.append(ValidationIssue(
                "HEIGHT_EXCEEDED", pallet_number, (index,),
                f"pallet {pallet_number}, case {index} ({_case_label(box, index)}), "
                f"{coordinates}: top z={z1} exceeds maximum {max_z}",
            ))
        else:
            valid_boxes.append((index, box))

    for index, box in valid_boxes:
        raw_weight = box.get("peso_caja")
        try:
            case_weight = float(raw_weight)
        except (TypeError, ValueError):
            case_weight = float("nan")
        if not math.isfinite(case_weight) or case_weight <= 0:
            issues.append(ValidationIssue(
                "INVALID_CASE_WEIGHT", pallet_number, (index,),
                f"pallet {pallet_number}, case {index} ({_case_label(box, index)}), "
                f"coordinates {box}: peso_caja must be finite and positive",
            ))
        else:
            cargo_weight_kg += case_weight

    for left_pos, (left_index, left) in enumerate(valid_boxes):
        for right_index, right in valid_boxes[left_pos + 1:]:
            if cuboids_overlap(left, right):
                issues.append(ValidationIssue(
                    "OVERLAP", pallet_number, (left_index, right_index),
                    f"pallet {pallet_number}, cases {left_index} ({_case_label(left, left_index)}) "
                    f"and {right_index} ({_case_label(right, right_index)}) overlap: "
                    f"case {left_index} coordinates {left}; case {right_index} coordinates {right}",
                ))

    for index, box in valid_boxes:
        if box["z_cm"] <= base_z + EPS_CM:
            continue
        support = exact_support_result(
            box["x_cm"], box["y_cm"], box["ancho_cm"], box["largo_cm"],
            box["z_cm"],
            [other for other_index, other in valid_boxes if other_index != index],
            config,
        )
        if not support.supported:
            issues.append(ValidationIssue(
                "UNDER_SUPPORTED", pallet_number, (index,),
                f"pallet {pallet_number}, case {index} ({_case_label(box, index)}), "
                f"coordinates {box}: support ratio {support.support_ratio:.6f} "
                f"({support.contact_area_cm2:.6f} cm2) is below required "
                f"{_get_config(config, 'MIN_SUPPORT_RATIO', 1.0):.6f}",
            ))

    issues.extend(_station_order_issues(pallet_number, valid_boxes))
    load_issues, load_diagnostics = _load_bearing_assessment(pallet_number, valid_boxes)
    issues.extend(load_issues)
    diagnostics = list(load_diagnostics)

    tare_weight = _get_config(config, "PALLET_TARE_WEIGHT_KG", None)
    max_gross = _get_config(config, "MAX_MIXED_PALLET_GROSS_WEIGHT_KG", None)
    gross_weight = None
    if tare_weight is None or max_gross is None:
        issues.append(ValidationIssue(
            "WEIGHT_LIMIT_UNCONFIGURED", pallet_number, tuple(index for index, _ in valid_boxes),
            f"pallet {pallet_number}: MAX_MIXED_PALLET_GROSS_WEIGHT_KG and "
            f"PALLET_TARE_WEIGHT_KG are required for gross-weight validation",
        ))
    else:
        tare_weight = float(tare_weight)
        max_gross = float(max_gross)
        gross_weight = tare_weight + cargo_weight_kg
        if gross_weight > max_gross + EPS_CM:
            issues.append(ValidationIssue(
                "OVERWEIGHT", pallet_number, tuple(index for index, _ in valid_boxes),
                f"pallet {pallet_number}: gross weight {gross_weight:.3f} kg "
                f"(tare {tare_weight:.3f} + cargo {cargo_weight_kg:.3f}) exceeds "
                f"limit {max_gross:.3f} kg",
            ))

    return ValidationResult(not issues, tuple(issues), tuple(sorted(set(diagnostics))), gross_weight)


def validate_order_geometry(pallets, config) -> ValidationResult:
    issues = []
    diagnostics = []
    gross_weight = 0.0
    has_weight = True
    for pallet in pallets:
        result = validate_pallet_geometry(pallet, config)
        issues.extend(result.issues)
        diagnostics.extend(result.diagnostics)
        if result.gross_weight_kg is None:
            has_weight = False
        else:
            gross_weight += result.gross_weight_kg
    return ValidationResult(
        not issues, tuple(issues), tuple(sorted(set(diagnostics))),
        gross_weight if has_weight else None,
    )


def raise_if_invalid_order_geometry(pallets, config) -> None:
    result = validate_order_geometry(pallets, config)
    if not result.valid:
        raise InvalidPalletGeometryError(result)
