# CONUS post-processing scripts

Analyze the finished runs in `..`. They use only the standard library, so they
run against the system python on the cluster with no modules loaded.

| script | purpose |
| --- | --- |
| `collect_times.py` | elapsed times and speedup over the whole sweep |
| `sum_memory.py` | memory manager totals per rank, per node, and per run |
| `scaling.py` | fit the run times and recommend sbatch wall times |

The scaling tables and figures, for CONUS and any other model, are made by the
scripts in [`scaling/`](../../scaling/README.md).

## Layout

The scripts locate everything from their own position, so they take no
arguments in the usual case:

```
$BASEDIR/
  models/base/          mfsim.nam, ngwm_NNNp.hpc, submit_conus.sh
  models/base/logs/     NNNp-<jobid>.out, read for ranks per node
  models/scripts/       partitioning, generates the HPC files
  results/results_NNNp/ mfsim.pN.lst
  results/scripts/      this directory
```

`../` is scanned for `results_NNNp` directories and `../../models/base/logs` for
the slurm logs. Both can be overridden with a positional argument and
`--logdir`.

## Use

```bash
./collect_times.py                 # elapsed times, speedup, projected T(1)
./sum_memory.py                    # one line per run
./sum_memory.py ../results_016p    # per-rank and per-node breakdown of one run
./scaling.py                       # fit and wall times
```

`collect_times.py` prints a `RUNTIMES` block at the end; paste it into
`scaling.py` to fold new runs into the fit. Entries are `ranks: (seconds, ppn)`,
and only runs at the reference 8 ranks per node are fit, because fewer ranks per
node means more memory bandwidth per rank and a point that does not belong on
the same curve.

Speedup is reported against the smallest rank count present, and also against a
`T(1)` projected from the fit. A real single-rank run is not possible here, and
1 rank is far outside the measured range, so treat that column as indicative.

## The sweep as of 2026-08-14

| ranks | ppn | nodes | mdl/rank | elapsed | speedup vs 8 | outer | inner | s/inner | total GB | GB/node |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 4 | 2 | 32 | 10:08:51 | 1.00 | 307 | 9,462 | 3.861 | 189.4 | 95.5 |
| 16 | 8 | 2 | 16 | 05:35:13 | 1.82 | 307 | 9,490 | 2.119 | 197.8 | 99.0 |
| 32 | 8 | 4 | 8 | 04:32:59 | 2.23 | 602 | 12,437 | 1.317 | 209.0 | 55.2 |
| 64 | 8 | 8 | 4 | 03:09:16 | 3.22 | 605 | 18,711 | 0.607 | 226.1 | 32.9 |
| 128 | 8 | 16 | 2 | 02:21:17 | 4.31 | 662 | 23,983 | 0.353 | 253.0 | 18.5 |
| 256 | 8 | 32 | 1 | 01:58:29 | 5.14 | 1,008 | 41,729 | 0.170 | 292.5 | 12.5 |

Models per rank is read from the `ngwm_NNNp.hpc` file that `slurm.batch` copies
into each results directory, so it reflects the partition the run actually used,
and shows a range rather than a single number if a partition is uneven.

### The solver does not do a fixed amount of work

Wall-clock scaling looks poor, 5.1x on 32x the ranks, and an Amdahl fit of the
runs at 8 ranks per node reads it as a 36% non-scaling fraction. That fit is
misleading. The iteration counts are not constant: inner iterations grow 4.4x
from 8 to 256 ranks and outer iterations 3.3x, because more partitions means a
weaker block preconditioner.

Separating the two effects, per inner iteration:

| ranks | s/inner | per-iter speedup | inner vs 8 ranks |
| ---: | ---: | ---: | ---: |
| 8 | 3.861 | 1.0 | 1.00 |
| 16 | 2.119 | 1.8 | 1.00 |
| 32 | 1.317 | 2.9 | 1.31 |
| 64 | 0.607 | 6.4 | 1.98 |
| 128 | 0.353 | 10.9 | 2.53 |
| 256 | 0.170 | 22.7 | 4.41 |

An inner iteration gets 22.7x faster on 32x the ranks, about 71% parallel
efficiency, which is respectable. Nearly all of it is then given back by having
to do 4.4x as many iterations. The limit is the partitioning's effect on solver
convergence, not the MPI implementation, so the lever is IMS settings rather
than more ranks.

Total memory grows with rank count, 189 GB at 8 to 293 GB at 256, because every
additional partition boundary duplicates its halo. Per node it still falls, so
more ranks always relieves memory pressure, just less than proportionally.

The 8-rank run used 4 ranks per node because 189 GB on one 256 GB rome node left
too little headroom. It came in at 10:08:51 against a 9:44 fit, so the extra
memory bandwidth per rank did not measurably help; this model is limited by its
serial fraction, not by bandwidth.

The memory manager totals do not include the solver, MPI buffers, or I/O, and
the unit of that table varies with its magnitude (the script reads it from the
header rather than assuming). `sacct -j <jobid> --format=JobID,MaxRSS,MaxVMSize`
gives the real resident set.
