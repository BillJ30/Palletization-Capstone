"""Independent post-pack release audit."""

from collections import Counter
from dataclasses import dataclass
import math

from pallet_validation import validate_order_geometry


@dataclass(frozen=True)
class ReleaseAuditResult:
    valid: bool
    issues: tuple[str, ...]
    validation_issues: tuple[object, ...]
    deterministic_fingerprint: tuple


def audit_packed_order(result, requested_lines, config):
    """Audit conservation and exact geometry immediately before export."""
    pallets = result.get("palets_picking", [])
    requested = Counter()
    requested_by_description = Counter()
    for line in requested_lines:
        requested[int(line.articulo)] += float(line.cajas_linea)
        requested_by_description[line.descripcion] += float(line.cajas_linea)
    placed = Counter()
    placed_by_description = Counter()
    has_article_ids = False
    issues = []
    fingerprint = []
    for pallet in pallets:
        for index, box in enumerate(pallet.get("cajas_3d", [])):
            article = box.get("articulo")
            if article is None:
                if requested_lines:
                    issues.append(f"pallet {pallet.get('numero')}, case {index}: missing article identifier")
            else:
                has_article_ids = True
                placed[int(article)] += 1
            placed_by_description[box.get("descripcion", "")] += 1
            for field in ("x_cm", "y_cm", "z_cm", "ancho_cm", "largo_cm", "alto_cm", "peso_caja"):
                try:
                    if not math.isfinite(float(box[field])) or float(box[field]) <= 0 and field not in ("x_cm", "y_cm", "z_cm"):
                        issues.append(f"pallet {pallet.get('numero')}, case {index}: invalid {field}")
                except (KeyError, TypeError, ValueError):
                    issues.append(f"pallet {pallet.get('numero')}, case {index}: missing/invalid {field}")
            fingerprint.append((pallet.get("numero"), index, tuple(sorted((key, repr(value)) for key, value in box.items()))))
    if has_article_ids and requested != placed:
        issues.append(f"article case conservation mismatch: requested={dict(requested)}, placed={dict(placed)}")
    elif requested_lines and not has_article_ids and requested_by_description != placed_by_description:
        issues.append(
            "case conservation mismatch by description: "
            f"requested={dict(requested_by_description)}, placed={dict(placed_by_description)}"
        )
    validation = validate_order_geometry(pallets, config)
    issues.extend(issue.message for issue in validation.issues)
    return ReleaseAuditResult(
        valid=not issues,
        issues=tuple(issues),
        validation_issues=validation.issues,
        deterministic_fingerprint=tuple(fingerprint),
    )


def assert_release_ready(result, requested_lines, config):
    audit = audit_packed_order(result, requested_lines, config)
    if not audit.valid:
        raise ValueError("Release audit failed: " + "; ".join(audit.issues[:5]))
    return audit
