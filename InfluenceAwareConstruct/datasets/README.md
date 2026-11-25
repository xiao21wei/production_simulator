# Dataset

This directory contains the 10 Brandimarte instances used by the
`InfluenceAwareConstruct` experiment.

For every instance, the scheduler requires a pair of files with the same
relative path:

```text
raw/Brandimarte/BrandimarteMkN.fjs
add/Brandimarte/BrandimarteMkN.fjs
```

## Raw files

`raw/Brandimarte/*.fjs` contains the standard Brandimarte FJSP processing
times, job operation counts, eligible machines and operation-machine
processing times.

## Additional files

`add/Brandimarte/*.fjs` contains the multi-objective extension data required
by this implementation:

1. Processing energy for every operation-machine option.
2. Job weight, ready time, due time, earliness penalty and tardiness penalty.
3. A symmetric machine-to-machine transport-time matrix.
4. A symmetric machine-to-machine transport-energy matrix.

The checked-in additional files were generated with random seed `42` and the
following ranges:

| Field | Range |
| --- | --- |
| Processing energy | 4-15 |
| Job weight | 1-5 |
| Ready time | 0-20 |
| Due time | ready time + 1.5 x estimated job duration |
| Earliness/tardiness penalty | 1-10 |
| Transport time | 1-3 |
| Transport energy | 1-4 |

Use `scripts/generate_add_data.py` to create compatible additional files for
new raw instances. The checked-in `Brandimarte` additional files are the
reference data for reproducing the report table; do not overwrite them when
the exact published numbers must be reproduced. Regeneration can introduce
small due-time rounding differences if the source raw files were prepared
with an older version of the generator.
