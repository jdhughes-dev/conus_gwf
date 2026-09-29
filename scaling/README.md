# Scaling tables and figures

Speedup, efficiency, iteration counts, and memory for MODFLOW 6 parallel runs,
as a LaTeX table and a figure. Not tied to one model: CONUS, saltfingers3d, and
bigsquare are all made the same way. Each script has `-h` help.

| script | purpose |
| --- | --- |
| `mf6_runs.py` | read the listings; timing, iterations, memory, replicate selection; writes a CSV |
| `TableScaling.py` | LaTeX tabular of the manuscript timing table, from the CSV |
| `PlotScaling.py` | speedup and efficiency figure, from the CSV |
| `data/` | the CSVs, one per model |

The figures and tables rebuild from `data/` alone, so a clone needs no access to
Snellius unless the runs change.

## Setup

- An ssh key that logs in to Snellius without a password prompt, loaded in the
  agent or named for the host in `~/.ssh/config`. Only needed to read new runs.
- `python3` for `mf6_runs.py` and `TableScaling.py`, which use only the
  standard library.
- The `conus` conda environment for `PlotScaling.py` (matplotlib and flopy).

## Use

From this directory:

```bash
# 1. read the listings on Snellius; writes data/saltfingers3d.csv
./mf6_runs.py /projects/0/prjs0960/saltfingers3D --remote --user <name>

# 2. table and figure from the CSV
./TableScaling.py data/saltfingers3d.csv                    # tables/saltfingers3d.tex
conda run -n conus ./PlotScaling.py data/saltfingers3d.csv  # figures/scaling/saltfingers3d/
```

`--user` defaults to `jhughes` and `--host` to `snellius.surf.nl`. With
`--remote` the script is sent over ssh and run by the system python on the
cluster, so nothing is copied to or written on Snellius, and the CSV comes back
as `data/<model>.csv` (`--csv` to name it). The report it prints is the same as
a local run.

The models run so far:

| model | directory on Snellius | tag | CSV |
| --- | --- | --- | --- |
| CONUS DIS | `/projects/0/prjs0960/conus_sweep/results` | `default` | `data/conus_sweep.csv` |
| CONUS DISV | `/projects/0/prjs0960/conus_sweep/results` | `disv` | `data/conus_sweep.csv` |
| saltfingers3d | `/projects/0/prjs0960/saltfingers3D` | | `data/saltfingers3d.csv` |
| bigsquare | `/projects/0/prjs0960/bigsquare` | | `data/bigsquare.csv` |

A model with more than one tag needs `--tag` for the table and figure:

```bash
./mf6_runs.py /projects/0/prjs0960/conus_sweep/results --remote     # data/conus_sweep.csv
./TableScaling.py data/conus_sweep.csv --tag disv                   # tables/conus_sweep_disv.tex
conda run -n conus ./PlotScaling.py data/conus_sweep.csv --tag disv # figures/scaling/conus_sweep/scaling_disv.*
```

On the cluster, `mf6_runs.py` and `TableScaling.py` also take a model directory
in place of a CSV:

```bash
./mf6_runs.py /projects/0/prjs0960/bigsquare --csv bigsquare.csv
./TableScaling.py /projects/0/prjs0960/bigsquare
```

## How runs are found and selected

A run is a `results_P[_tag]` directory with `mfsim.p0.lst` (or `mfsim.lst` for
one rank), found in the model directory or one level below it, so `results_P`,
`bigsquare_Pp/results_P`, and `run_N/results_P` all work. An untagged
`results_P` directory is tagged `default`; for CONUS that is the DIS grid and
`disv` the DISV grid, both run with ILUT.

`run_N` directories are replicates. Only partition counts every replicate
finished are kept, and the replicate with the middle total inner iterations is
used (ties go to the middle elapsed time). Outer and inner iterations are summed
over every time step and solution.

Memory is the memory manager total summed over every rank's listing. When the
selected replicate did not keep a listing for every rank, another replicate
that did is used, since the allocation depends only on the partitioning.

The total simulation time is the profiler Run total, else the elapsed run time.
A run without the profiler has no linear solve time, so the figure has only
panel A, at half the width, and the table no linear solution columns
(bigsquare).

## Outputs

Figures go in `figures/scaling/<model>/` and tables in
`tables/<model>[_<tag>].tex` at the top of the repository, the model name defaulting to the source name.
Speedup and efficiency refer to the fewest partitions unless `--ref` is given.

Panel A is labeled with the model name, without a trailing `_sweep`, and the tag
(`conus disv`); `--label` replaces it. `--legend` moves the legend to another
corner of panel A, or `outside` above the panels when no corner is clear.

The table file is the `tabular` only, so the manuscript keeps its float,
caption, label, and `\sisetup`, and inputs the file in place of its tabular.
