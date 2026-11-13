"""Canonical physical specifications for order/pick-unit SKUs."""

from dataclasses import asdict, dataclass
import json
import math

import pandas as pd


EPS_CM = 1e-6
PALLET_AREA_CM2 = 80.0 * 120.0


@dataclass(frozen=True)
class SKUPhysicalSpec:
    articulo: int
    pick_uom: str
    length_cm: float
    width_cm: float
    height_cm: float
    case_weight_kg: float
    cases_per_layer_reference: int | None
    layers_per_pallet_reference: int | None
    source_dimensions: str
    source_weight: str
    source_capacity: str | None
    station_index: int | None = None
    station_name: str | None = None
    sequence_version: str | None = None
    max_load_above_kg: float | None = None


@dataclass(frozen=True)
class SKUValidationReport:
    missing: tuple[dict, ...]
    conflicting: tuple[dict, ...]
    unit_incompatible: tuple[dict, ...]
    candidate_rows: int
    valid_specs: int

    @property
    def invalid_specs(self):
        return len(self.missing) + len(self.conflicting) + len(self.unit_incompatible)

    def to_dict(self):
        return asdict(self) | {"invalid_specs": self.invalid_specs}

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


class InvalidSKUContractError(ValueError):
    """Raised when an order line has no valid canonical physical specification."""

    def __init__(self, articulo, issue):
        self.articulo = articulo
        self.issue = issue
        super().__init__(
            f"SKU {articulo} has no valid canonical pick-unit spec: "
            f"{issue.get('code', 'INVALID')} ({issue.get('message', '')})"
        )


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _int_reference(value):
    value = _number(value)
    if value is None or value <= 0:
        return None
    return int(round(value))


def _record_issue(code, articulo, message):
    return {"code": code, "articulo": int(articulo), "message": message}


def _source_rows(frame, article_column):
    if article_column not in frame.columns:
        return {}
    result = {}
    for _, row in frame.iterrows():
        articulo = _number(row.get(article_column))
        if articulo is not None:
            result.setdefault(int(articulo), []).append(row)
    return result


def build_sku_master(dimensions_df, capacity_df, route=None, area_tolerance=EPS_CM):
    """Build canonical specs and a machine-readable validation report."""
    dimensions = _source_rows(dimensions_df, "Material")
    capacity = _source_rows(capacity_df, "Material")
    article_ids = sorted(set(dimensions) | set(capacity))
    missing = []
    conflicting = []
    unit_incompatible = []
    specs = []
    metadata = []

    for articulo in article_ids:
        drows = dimensions.get(articulo, [])
        crows = capacity.get(articulo, [])
        if not drows:
            missing.append(_record_issue("MISSING_DIMENSIONS", articulo, "no dimensions source row"))
            continue
        if not crows:
            # Exact dimensions and weight remain usable without reference capacity.
            crows = [None]

        d = drows[0]
        c = crows[0]
        d_uom = str(d.get("UMB", "")).strip()
        c_uom = "" if c is None else str(c.get("UMB", "")).strip()
        length = _number(d.get("Longitud_cm"))
        width = _number(d.get("Ancho_cm"))
        height = _number(d.get("Altura_cm"))
        weight = _number(d.get("Peso bruto"))
        capacity_ref = None if c is None else _int_reference(c.get("Cajas/Capa"))
        layers_ref = None if c is None else _int_reference(c.get("Capas/Palet"))

        comparable_values = [
            (str(row.get("UMB", "")).strip(), _number(row.get("Longitud_cm")),
             _number(row.get("Ancho_cm")), _number(row.get("Altura_cm")),
             _number(row.get("Peso bruto")))
            for row in drows
        ]
        if len(set(comparable_values)) > 1:
            conflicting.append(_record_issue(
                "CONFLICTING_DIMENSIONS", articulo,
                f"multiple dimension/weight specs: {comparable_values}",
            ))
            continue
        capacity_values = [
            (str(row.get("UMB", "")).strip(), _int_reference(row.get("Cajas/Capa")),
             _int_reference(row.get("Capas/Palet")), _number(row.get("BRUTO ZPA")))
            for row in crows if row is not None
        ]
        if len(set(capacity_values)) > 1:
            conflicting.append(_record_issue(
                "CONFLICTING_CAPACITY", articulo,
                f"multiple capacity/weight specs: {capacity_values}",
            ))
            continue

        if not d_uom or (c is not None and not c_uom):
            unit_incompatible.append(_record_issue(
                "MISSING_UOM", articulo, f"dimensions UMB={d_uom!r}, capacity UMB={c_uom!r}",
            ))
            continue
        if c is not None and d_uom != c_uom:
            unit_incompatible.append(_record_issue(
                "UOM_MISMATCH", articulo, f"dimensions UMB={d_uom!r}, capacity UMB={c_uom!r}",
            ))
            continue
        if any(value is None or value <= 0 for value in (length, width, height, weight)):
            missing.append(_record_issue(
                "INVALID_PHYSICAL_VALUES", articulo,
                f"length={length}, width={width}, height={height}, weight={weight}",
            ))
            continue

        if capacity_ref is not None:
            area_ratio = capacity_ref * length * width / PALLET_AREA_CM2
            if area_ratio > 1.0 + area_tolerance:
                unit_incompatible.append(_record_issue(
                    "LAYER_AREA_EXCEEDED", articulo,
                    f"declared_layer_area_ratio={area_ratio:.6f} exceeds 1.0",
                ))
                continue

        source_capacity = None if c is None else "productos_con_dimensiones_2.csv"
        route_entry = None if route is None else route.get(str(d.get("Grupo art.", "")).strip())
        specs.append(SKUPhysicalSpec(
            articulo=articulo,
            pick_uom=d_uom,
            length_cm=length,
            width_cm=width,
            height_cm=height,
            case_weight_kg=weight,
            cases_per_layer_reference=capacity_ref,
            layers_per_pallet_reference=layers_ref,
            source_dimensions="Packaging_Logistics_Data.csv",
            source_weight="Packaging_Logistics_Data.csv",
            source_capacity=source_capacity,
            station_index=None if route_entry is None else route_entry.station_index,
            station_name=None if route_entry is None else route_entry.station_name,
            sequence_version=None if route_entry is None else route_entry.sequence_version,
            max_load_above_kg=None,
        ))
        metadata.append({
            "ARTICULO": articulo,
            "SKU_PICK_UOM": d_uom,
            "ALTO_CAJA_CM": height,
            "ANCHO_CAJA_CM": width,
            "LARGO_CAJA_CM": length,
            "CASE_WEIGHT_KG": weight,
            "CAJAS_POR_CAPA_REFERENCE": capacity_ref,
            "CAPAS_POR_PALET_REFERENCE": layers_ref,
            "SKU_SPEC_VALID": True,
            "Grupo art.": d.get("Grupo art.", None),
            "NUM_ZPA": d.get("NUM_ZPA", None),
            "Densidad_kg_m3": d.get("Densidad_kg_m3", None),
            "Estabilidad": d.get("Estabilidad", None),
            "Familia_detectada": d.get("Familia_detectada", None),
            "BRUTO ZPA": None if c is None else c.get("BRUTO ZPA", None),
            "STATION_INDEX": None if route_entry is None else route_entry.station_index,
            "STATION_NAME": None if route_entry is None else route_entry.station_name,
            "ROUTE_SEQUENCE_VERSION": None if route_entry is None else route_entry.sequence_version,
            "MAX_LOAD_ABOVE_KG": None,
        })

    report = SKUValidationReport(
        missing=tuple(missing), conflicting=tuple(conflicting),
        unit_incompatible=tuple(unit_incompatible),
        candidate_rows=len(article_ids), valid_specs=len(specs),
    )
    master = pd.DataFrame(metadata)
    if master.empty:
        master = pd.DataFrame(columns=["ARTICULO", "SKU_SPEC_VALID"])
    master.attrs["sku_validation_report"] = report
    master.attrs["sku_specs"] = tuple(specs)
    return master, report
