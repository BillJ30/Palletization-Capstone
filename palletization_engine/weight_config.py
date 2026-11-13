"""Hard pallet-weight and load-bearing configuration.

The mixed-pallet gross limit is an explicit configuration value and is not
derived from observed order data. The warehouse has not supplied a pallet tare
weight in this repository, so the temporary assumption is 0.0 kg; replace it
when the tare is confirmed. Gross weight always means tare plus placed cases.
"""

MAX_MIXED_PALLET_GROSS_WEIGHT_KG = 1000.0
PALLET_TARE_WEIGHT_KG = 0.0

assert MAX_MIXED_PALLET_GROSS_WEIGHT_KG > 0.0
assert PALLET_TARE_WEIGHT_KG >= 0.0

