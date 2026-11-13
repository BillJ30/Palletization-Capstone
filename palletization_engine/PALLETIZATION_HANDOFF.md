# Palletization Handoff Report

### Current Pallet-Building Logic
The current solution works like this:
Receive the order
The system receives either an existing order number or manually entered materials and quantities.
Manual materials are checked against the validated SKU master before packing.

Prepare the order
Each product receives its real case dimensions, case weight, allergen status, and warehouse station.
Picking products are sorted by warehouse station order.
Allergen products are handled separately.

Open the first pallet
The pallet footprint is:120 cm in x
80 cm in y

The wooden pallet occupies the first 14.4 cm of height.
Cases can use cargo space up to 165.6 cm, with a total top height limit of 180 cm.

Try to build a complete layer
If several cases of the same SKU remain, the planner first tries to create a compact 2D pattern.
It tests:normal orientation;
90-degree rotation;
rows and columns;
simple shelf combinations.

It chooses the pattern with the most cases, then the most covered area, then the fewest gaps and best balance.

Validate the planned layer
Every planned case is checked using its real dimensions.
The layer must:stay inside 120 × 80 cm;
have no positive-volume overlap;
have exact support;
stay below 180 cm;
stay below the gross-weight limit.


Place the layer case by case
Even though the pattern is planned as a group, cases are recorded one by one in warehouse order.
Each actual placement is checked again before being accepted.

Use exact individual placement when needed
If a full layer pattern is not possible, the system searches for one case at a time.
It tries exact case edges, both orientations, and exact top surfaces.
The 4 cm heightmap may help search, but it cannot approve overlap, support, height, or boundaries.

Open a new pallet when necessary
If the next case cannot fit anywhere valid on the current pallet, the current pallet is closed.
The remaining cases are moved to a new pallet.
This happens when the current pallet has no valid space because of footprint, support, height, or weight.

Continue until all cases are placed
The process repeats layer planning, exact validation, fallback placement, and pallet opening until the order is complete.

Validate before export
Before writing the CSV, the system independently checks:case counts;
dimensions and weights;
bounds;
height;
overlaps;
support;
station order;
gross weight.

If anything is invalid, the CSV is not exported.

In simple terms:
Sort products by warehouse order
-> plan the largest compact layer possible
-> validate every case exactly
-> place the layer
-> repeat upward
-> if the pallet cannot accept the next case, open another pallet
-> validate everything again
-> export only if valid
The main difference from the original solution is that the system no longer blindly places cases one at a time using approximate grid space. It now plans compact layers first, while exact physical geometry remains the final authority.


## 1. Purpose

This application receives a customer order containing products and case quantities. It decides how those cases should be distributed across wooden pallets.

The goal is not simply to put as many cases as possible onto a pallet. The result must also be physically possible and operationally sensible:

- cases must stay inside the pallet footprint;
- cases must not overlap;
- upper cases must have real support;
- the total height and gross weight limits must be respected;
- warehouse station order must be respected;
- invalid or incomplete product data must not silently enter the optimizer;
- exported placements must pass an independent final audit.

The current canonical geometry is:

| Setting | Value |
|---|---:|
| Pallet x length | 120.0 cm |
| Pallet y width | 80.0 cm |
| Wooden base | 14.4 cm |
| Maximum total height | 180.0 cm |
| Maximum cargo height above base | 165.6 cm |
| Maximum mixed-pallet gross weight | 1000.0 kg |

The first case starts at `z=14.4`. A case is valid only when its top is no higher than `180.0 cm`.

## 2. How To Run It

### Desktop UI

From the project directory:

```powershell
python order_ui.py
```

The UI loads the input data in the background. It supports two modes:

- **Existing order:** enter an order number from the logistics dataset.
- **Manual order:** enter one material and quantity per line, for example `80,50`.

After processing, the UI displays a textual result and enables CSV export. The export button is only enabled after successful order processing.

### Command-line runner

```powershell
python run_csv.py
```

`run_csv.py` also exposes reusable functions for other applications:

- `cargar_base_datos()` loads the data;
- `resolver_pedido(...)` processes an existing order;
- `resolver_pedido_manual(...)` processes manually entered materials;
- `exportar_pedido(...)` writes the validated visualization CSV.

## 3. Overall Runtime Flow

The normal flow is:

```text
UI or CLI input
    -> load and normalize data
    -> validate SKU and route information
    -> convert rows into order-line objects
    -> sort picking lines by warehouse station
    -> build exact pallet layers
    -> place and revalidate each case
    -> validate the complete order independently
    -> export only validated placements
```

The important design principle is that the optimizer proposes placements, but the validator is the final authority. A good score cannot make an invalid placement acceptable.

## 4. Data Loading And Product Preparation

### Logistics CSV

`logistics_csv.py` reads `inputs/dataset_logistico_lineas.csv` with Python's `csv` module instead of trusting a single `pandas.read_csv` call.

Some physical records are wrapped inside one quoted field. The reader detects that shape and parses the field a second time. It checks that every final row has exactly the same number of fields as the header.

If a row cannot be recovered, loading fails. It is not silently removed.

The reader records:

- physical records read;
- wrapped records repaired;
- records rejected;
- final DataFrame row count;
- unique numeric order count.

For the supplied dataset, the audited values are 568,871 records, 39,759 repaired records, zero rejected records, and 41,405 unique orders.

### SKU master

`sku_master.py` builds one canonical physical specification per article and pick unit.

The specification contains the case length, width, height, weight, unit of measure, route information, and optional capacity references.

The code rejects or quarantines:

- missing dimensions or weight;
- non-positive or non-finite physical values;
- conflicting duplicate specifications;
- mismatched units of measure;
- capacity metadata that would imply more case area than the pallet can physically contain.

`Cajas/Capa` and `Capas/Palet` are treated as reference information. They are not allowed to override exact geometry.

The validation report is stored on the resulting DataFrame, so the full SKU-master audit is available without printing hundreds of warnings during normal UI startup.

### Warehouse route

`station_route.py` loads `station_route.csv`. Each route entry contains a station index, station name, and sequence version.

Picking lines are sorted by station index. The sort is stable, so lines within one station retain their original order.

If an in-scope picking family has no resolved station mapping, processing fails before packing. There is no silent rank-99 fallback in the active route validation.

## 5. Order Input Paths

### Existing order

`run_csv.resolver_pedido` filters the normalized DataFrame by order number, converts each row with `fila_a_linea`, and sends the resulting `LineaPedido` objects to `procesar_pedido_dict`.

### Manual order

`run_csv.construir_pedido_manual` parses lines in comma, semicolon, or whitespace format. It looks up every material in the validated product master.

It collects all invalid materials before failing. The UI then lists every invalid material and explains whether it was not found or lacked a compatible SKU specification. The user can either cancel or remove all invalid materials and continue with the valid lines only.

This prevents an invalid manual material from reaching the packer and prevents the user from having to discover invalid materials one at a time.

## 6. Main Packing Process

The main orchestration is in `palet_conformador.py`.

`procesar_pedido_dict` first separates the input into whole pallets, semi-pallets, and picking lines. Picking lines are split into normal and allergen groups. Normal and allergen products are processed separately.

For each picking group, the code creates `SubLinea` objects containing:

- article and description;
- requested case quantity;
- exact dimensions;
- case weight;
- station index;
- allergen status;
- reference layer metadata;
- optional load-bearing data.

The default operational policy is `single_active`: the current pallet is the pallet a picker is working on. The optional `multiple_open` policy can consider all currently accessible pallets, but the UI does not expose a switch for it.

## 7. Exact Geometry

The old problem was that a 4 cm heightmap could represent a real 39.9 cm edge as approximately 36 cm. That created false free space and allowed overlapping exported boxes.

The current code keeps the heightmap as a fast surface aid, but not as the final geometric authority.

`cuboids_overlap` checks the exact x, y, and z intervals of two cases. Two boxes overlap only when all three axes have a positive-volume intersection. Touching faces or edges are allowed.

`buscar_posicion_optima` now:

1. tries both orientations of the case;
2. creates candidate x/y coordinates from exact edges of already placed cases;
3. includes regular grid-like coordinates as an additional search source;
4. considers exact top surfaces as possible base heights;
5. checks height and footprint bounds;
6. checks exact support;
7. checks exact cuboid collision.

The heightmap can help locate candidates, but it cannot authorize an invalid coordinate.

## 8. Exact Support

`pallet_validation.exact_support_result` calculates support from real rectangles, not heightmap cells.

For a first-layer case, the wooden deck provides full support if the footprint is inside the pallet.

For an upper case:

1. the candidate has one exact base height;
2. only boxes whose top is at that same height are considered supports;
3. each support rectangle is clipped to the candidate footprint;
4. overlapping support rectangles are merged mathematically;
5. the union area is divided by the candidate footprint area.

The default minimum support ratio is `1.0`, meaning a rigid case must be fully supported. Cases at different top heights do not form one support plane.

## 9. Layer Planning

`layer_patterns.py` addresses the second major problem: placing cases individually creates scattered islands and towers.

For a homogeneous SKU, the planner creates exact two-dimensional candidate patterns using:

- the normal orientation;
- the 90-degree rotated orientation;
- complete rows and columns;
- bounded shelf or guillotine combinations.

The planner scores patterns lexicographically:

1. most cases on the layer;
2. largest exact covered area;
3. smallest unused area;
4. best center balance;
5. deterministic coordinate order.

The selected pattern is stored as `PlannedPlacement` records. It is then executed case by case in the picker sequence. Every actual execution is checked again for collision, support, height, and weight.

The planner completes a broad feasible layer before starting another height band. A representative 80-case test produces eight complete 9-case layers and one 8-case remainder layer, with zero overlaps.

The module also contains a conservative mixed-layer enumerator. Mixed layers require a common top height within the explicit construction tolerance. The main production path primarily uses homogeneous patterns and falls back to the existing exact case-by-case search when a homogeneous pattern is not useful.

## 10. Height, Weight, And New Pallets

Before a case is placed, the code checks projected gross weight. The current configured mixed-pallet limit is 1000 kg. Gross weight is cargo plus pallet tare; the repository currently uses a temporary tare value of 0 kg because the warehouse has not supplied a confirmed tare.

If a case cannot fit the current pallet because no valid surface remains, the remaining quantity is returned to the pallet orchestration loop. The current pallet is closed and a new pallet is opened. The case is retried on the new pallet.

This includes cases blocked by:

- footprint collision;
- lack of exact support;
- excessive height;
- gross weight.

The exception is a case that is individually larger than the available pallet height or weight limit. A new pallet cannot solve an individually impossible case, so that situation correctly stops with an error.

## 11. Pallet Selection Policy

`placement_optimization.py` defines `PlacementScore` as an ordered tuple rather than one weighted points total.

Only feasible candidate pallets are passed to the score. The score can then prefer:

- keeping the current pallet;
- completing the current layer;
- lower unused layer area;
- flatter surfaces;
- lower fragmentation;
- better center of mass;
- lower worker effort;
- deterministic ties.

This separation is important: an invalid placement is removed before scoring and cannot win because of a good utilization score.

`single_active` is the default. `multiple_open` is available for a warehouse operation where returning to earlier open pallets is physically allowed.

The module also contains geometry-based metrics such as layer union utilization, envelope volume utilization, top-height spread, center-of-mass offset, and SKU/layer switches.

## 12. Independent Validation And Export

`pallet_validation.py` is intentionally independent of the placement search internals. It treats final `cajas_3d` records as ordinary cuboids and checks:

- required coordinates and dimensions;
- finite numeric values;
- positive dimensions and weights;
- x/y bounds;
- base height and total height;
- exact overlaps;
- exact support;
- station precedence;
- gross weight;
- conservative load-bearing limits when data exists.

`release_audit.py` adds order-level checks before export:

- requested versus placed case counts by article;
- missing or duplicated cases;
- article identifiers;
- deterministic placement fingerprint;
- all independent geometry-validation issues.

`exportar_pedido_a_csv_visualizacion` runs the validator and release audit before creating rows. It writes to a temporary sibling file and replaces the destination only after successful completion. Therefore an invalid result cannot be exported as `PLACED`, and an existing valid output is not partially overwritten.

The CSV now uses the total-pallet coordinate convention:

- x from 0 to 120;
- y from 0 to 80;
- z starting at 14.4;
- `Z_Reference=PALLET_TOTAL_COORDINATES`.

## 13. What Changed Compared With The Original Design

The original approach was essentially:

```text
find the lowest heightmap position
-> place one case
-> repeat
```

That approach was fast and visually compact in some outputs, but it could use rounded grid edges and create physical overlaps. When exact collision checks were added without a layer planner, the opposite problem appeared: cases were valid but could form scattered blocks and towers.

The current design combines both improvements:

1. exact geometry decides whether a placement is legal;
2. exact support decides whether an upper case can rest there;
3. layer patterns create compact two-dimensional groups;
4. route order determines which products are processed first;
5. hard constraints are checked before any optimization score;
6. a full pallet is closed and a new pallet is opened when the next case cannot fit;
7. an independent release audit protects the exported result.

This is the key conceptual change: optimization is allowed to choose among legal solutions, but it is never allowed to trade away physical validity.

## 14. File Responsibilities

| File | Responsibility |
|---|---|
| `order_ui.py` | Desktop interface, background loading, manual validation dialog, run/export actions |
| `run_csv.py` | Reusable UI/CLI adapter and manual/existing-order resolution |
| `palet_conformador.py` | Data enrichment, order orchestration, pallet construction, layer execution, CSV export |
| `logistics_csv.py` | Strict logistics CSV parsing and reconciliation metrics |
| `sku_master.py` | Canonical physical SKU specifications and SKU validation report |
| `station_route.py` | Warehouse station configuration and route validation |
| `layer_patterns.py` | Exact homogeneous and conservative mixed layer patterns |
| `pallet_validation.py` | Independent geometry, support, route, weight, and load validation |
| `release_audit.py` | Final article-count and release-readiness audit |
| `placement_optimization.py` | Lexicographic pallet selection and physical benchmark metrics |
| `promotion_capacity.py` | SKU-specific add-on capacity trials using the same packer and validator |
| `weight_config.py` | Explicit gross-weight and tare configuration |
| `station_route.csv` | Warehouse-controlled station sequence |

## 15. Compatibility Paths To Know About

The main picking path uses exact 3D placement when every line in the group has validated dimensions. `conformar_palets_3d` is therefore the path that produces the exact `cajas_3d` placements described in this report.

There is also a legacy fractional pallet path, `conformar_palets`, retained for compatibility with non-3D or non-picking situations. It uses pallet fractions and `Cajas/Palet`-style metadata rather than exact 3D placement. It should not be used as evidence of exact physical placement.

The exporter also has a formatting path for whole-pallet and semi-pallet lines. Those rows are generated from their layer metadata rather than from `cajas_3d`. If the project later needs one universal physical release audit for every product category, that compatibility path should be migrated to the same exact 3D representation.

## 16. Important Operational Settings

The following values are intentionally explicit and should be reviewed with the warehouse:

- maximum gross pallet weight;
- pallet tare weight;
- approved minimum support ratio;
- compression or load-bearing values;
- exact station route mapping;
- whether multiple pallets are physically accessible during picking;
- whether the visualizer should use total coordinates or a cargo-only display transformation.

The current code does not invent compression strength when no data is available. It reports `load_data_unavailable` and uses the approved station-order and exact-support rules instead.

## 17. Verification Status

The repository contains unit tests for geometry, support, height, layer planning, ingestion, manual-material validation, route sequencing, pallet validation, weight, SKU contracts, promotion capacity, and pallet policy selection.

The current test command is:

```powershell
python -m unittest discover -v
```

The current suite passes 60 tests. The most important packing regression is the 80-case layer test: it verifies 80 cases, eight full 9-case layers plus one 8-case remainder, and no exact overlaps.

"""
PalletVision – Palletization Visualisation Tool

Created and owned by:

Alexandre Gallais
Mohamad Bilal
Saif Rizvi


Developed as part of the UCD Capstone Project.
"""
