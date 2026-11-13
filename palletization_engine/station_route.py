"""Warehouse station-route configuration and validation."""

from dataclasses import dataclass
import csv
from pathlib import Path


DEFAULT_ROUTE_PATH = Path(__file__).with_name("station_route.csv")


@dataclass(frozen=True)
class StationRouteEntry:
    article_or_family: str
    station_index: int | None
    station_name: str
    sequence_version: str

    @property
    def resolved(self):
        return self.station_index is not None


class StationRouteError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        summary = "; ".join(issue["message"] for issue in self.issues[:10])
        super().__init__(f"Station route validation failed: {summary}")


def load_station_route(path=DEFAULT_ROUTE_PATH):
    entries = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        expected = {"article_or_family", "station_index", "station_name", "sequence_version"}
        if set(reader.fieldnames or ()) != expected:
            raise StationRouteError([{
                "code": "INVALID_ROUTE_SCHEMA",
                "message": f"expected columns {sorted(expected)}",
            }])
        for line_number, row in enumerate(reader, start=2):
            key = str(row["article_or_family"]).strip()
            raw_index = str(row["station_index"]).strip()
            station_index = None if raw_index in ("", "UNRESOLVED") else int(raw_index)
            entry = StationRouteEntry(
                article_or_family=key,
                station_index=station_index,
                station_name=str(row["station_name"]).strip(),
                sequence_version=str(row["sequence_version"]).strip(),
            )
            if not key:
                raise StationRouteError([{
                    "code": "EMPTY_ROUTE_KEY",
                    "message": f"line {line_number} has no article_or_family",
                }])
            if key in entries and entries[key] != entry:
                raise StationRouteError([{
                    "code": "CONFLICTING_ROUTE_MAPPING",
                    "message": f"line {line_number} conflicts for {key}",
                }])
            entries[key] = entry
    return entries


def validate_picking_route(df, route):
    issues = []
    picking = df[df["ES_PICKING"] == True]
    for key in sorted(picking["GRUPO_ART"].dropna().astype(str).str.strip().unique()):
        entry = route.get(key)
        if entry is None:
            issues.append({
                "code": "MISSING_ROUTE_MAPPING",
                "article_or_family": key,
                "message": f"no station mapping for picking family {key}",
            })
        elif not entry.resolved:
            issues.append({
                "code": "UNRESOLVED_ROUTE_MAPPING",
                "article_or_family": key,
                "message": f"station mapping for picking family {key} is unresolved",
            })
    if issues:
        raise StationRouteError(issues)


def station_for(entry_key, route):
    entry = route.get(str(entry_key).strip())
    if entry is None or not entry.resolved:
        raise StationRouteError([{
            "code": "MISSING_ROUTE_MAPPING",
            "article_or_family": str(entry_key),
            "message": f"no resolved station mapping for {entry_key}",
        }])
    return entry

