# conus_gwf

## Scaling tables and figures

[`scaling/`](scaling/README.md) makes the speedup, efficiency, iteration, and
memory tables and figures for MODFLOW 6 parallel runs on Snellius, for CONUS
and any other model. They rebuild from the CSVs in `scaling/data/`, written to
`tables/` and `figures/scaling/<model>/`.

The CONUS-specific post-processing (run times, memory per node, wall-time fits)
is in [`results/scripts/`](results/scripts/README.md).
