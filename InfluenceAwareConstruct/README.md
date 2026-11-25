# InfluenceAwareConstruct

This directory is a self-contained package for evaluating the
`InfluenceAwareConstruct` scheduling method and the comparison methods used
in the technical report.

## Included methods

The experimental comparison entry point runs:

```text
FIFO_SPT
FIFO_EET
MOPNR_SPT
MOPNR_EET
MWKR_SPT
MWKR_EET
InfluenceAwareConstruct
```

`InfluenceAwareConstruct` combines processing time, processing and transport
energy, machine load, machine queue availability, transport time, delivery
urgency and remaining-work criticality while constructing a feasible FJSP
schedule.

The full search path additionally includes Greedy Search, Genetic Algorithm,
Tabu Search and the combined multi-objective evaluation.

## Requirements

- CMake 3.16 or newer
- A C++20 compiler
- Python 3.9 or newer for the helper scripts

There are no external C++ libraries, optimization-solver licenses or Python
packages required by the scheduler itself.

## Build

```bash
cd InfluenceAwareConstruct
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"
```

The executable is:

```text
build/influence_aware_scheduler
```

## Run the initial-method comparison

Run all seven initial methods on one instance:

```bash
./build/influence_aware_scheduler \
  datasets/raw/Brandimarte/BrandimarteMk3.fjs \
  --compare-initial
```

The `InfluenceAwareConstruct` row contains the three objectives and the normalized
combined objective.

Run only `InfluenceAwareConstruct` through the convenience script:

```bash
python3 scripts/run_influence_aware.py \
  datasets/raw/Brandimarte/BrandimarteMk3.fjs
```

## Unified construction API

The executable also accepts a dataset path configuration and a selected
method. This mode supports both the split dataset layout used by the simulator
(`raw`, `add` and `delivery_cost`) and the older layout where delivery fields
are embedded in `add`:

```bash
./build/influence_aware_scheduler \
  --construct InfluenceAwareConstruct \
  --dataset-root ../datasets \
  --raw ../datasets/raw/fjsp.brandimarte.Mk03.m8j15c5.fjs \
  --add ../datasets/add/fjsp.brandimarte.Mk03.m8j15c5.fjs \
  --delivery-cost \
  ../datasets/delivery_cost/fjsp.brandimarte.Mk03.m8j15c5.fjs
```

The supported `--construct` values are:

```text
FIFO_SPT
FIFO_EET
MOPNR_SPT
MOPNR_EET
MWKR_SPT
MWKR_EET
InfluenceAwareConstruct
```

Successful requests print one JSON object containing the selected method,
source paths, makespan, delivery cost, total/processing/transport energy,
FIFO baseline, and machine/operation start and end times. Invalid paths,
inconsistent raw/add data, or unknown methods produce a non-zero exit status
with the reason on standard error.

The simulator exposes this entry point through:

```text
POST /api/model-test/construction
POST /api/influence-aware-reoptimize
POST /api/construction-reoptimize
```

The model-test endpoint returns the complete construction result for visual
inspection. Reoptimization endpoints apply the generated machine assignments
only to pending and scheduled operations in the selected process; the
simulator then recalculates transport, waiting and processing times from the
current simulation state. When manual reoptimization changes machine
assignments, the simulator remains paused while the dashboard animates each
operation from its pre-schedule pending-queue slot to its post-schedule slot,
then resumes only after the animation-complete acknowledgement.

## Reproduce the ten-instance report table

```bash
python3 scripts/compare_initial_methods.py
```

The default output is:

```text
results/initial_method_comparison.csv
```

The reference output used to prepare the report is retained as:

```text
results/expected_initial_method_comparison.csv
```

## Run multi-objective local search from InfluenceAware

The `--influence-aware` option forces the full search to start from
`InfluenceAwareConstruct` instead of automatically selecting the best initial
method:

```bash
./build/influence_aware_scheduler \
  datasets/raw/Brandimarte/BrandimarteMk3.fjs \
  --influence-aware 0 0.5 100 30 20 25
```

Arguments after `--influence-aware` are:

```text
<search_mode> <random_strategy> <max_repeat_count>
<max_iter_count> <population_size> <tabu_list_length>
```

`search_mode=0` prefers Greedy Search. The random-search branch selects a
Genetic Algorithm or Tabu Search according to `random_strategy`.

The last output line has this format:

```text
instance,makespan,cost,energy,fifo_makespan,fifo_cost,fifo_energy,HV
```

The program also has built-in safety limits of 6000 seconds, 1200 iterations
and `max_repeat_count` consecutive non-improving rounds.

## Data

The package contains the 10 Brandimarte instances used by the report:

```text
datasets/raw/Brandimarte/BrandimarteMk1.fjs ... BrandimarteMk10.fjs
datasets/add/Brandimarte/BrandimarteMk1.fjs ... BrandimarteMk10.fjs
```

The `add` files contain synthetic processing energy, delivery parameters and
transport matrices. See `datasets/README.md` for generation details.

When `--delivery-cost` is provided, job features are read from that file and
the `add` file is expected to contain only processing energy followed by the
transport-time and transport-energy matrices. When it is omitted, automatic
path inference first looks for `../delivery_cost/<instance>.fjs`; if absent,
the legacy `add` layout with embedded job features remains supported.

Create compatible additional files for new raw instances with:

```bash
python3 scripts/generate_add_data.py
```

If the exact report table must be reproduced, retain the checked-in
`datasets/add/Brandimarte` files instead of regenerating them. The current
generator produces the same format and ranges, but one checked-in Brandimarte
due time can differ by a one-unit rounding result from a fresh generation.

## Source map

| File | Responsibility |
| --- | --- |
| `src/Experiment.cpp` | InfluenceAwareConstruct and six comparison methods |
| `src/DataProc.cpp` | Data loading, graph decoding and objective calculation |
| `src/Schedule.cpp` | Schedule representation and critical-path calculation |
| `src/GreedySearch.cpp` | Greedy neighborhood search |
| `src/RandomSearch.cpp` | Genetic Algorithm and search orchestration |
| `src/TabuSearch.cpp` | Critical-path-driven Tabu Search |
| `src/main.cpp` | Command-line entry point |

## Notes

- Every raw file must have an identically named `add` file under the parallel
  `raw`/`add` directory tree.
- `InfluenceAwareConstruct` currently implements a machine-level four-factor
  weighted score and a lexicographic operation priority. It is related to, but
  not identical to, the five-factor formula described in report section 4.6.
- The scheduler uses `time(nullptr)` as its random seed, so repeated full
  searches may return different solutions.
