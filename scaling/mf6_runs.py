#!/usr/bin/env python
"""
Read the timing and solver work of MODFLOW 6 parallel runs from their listings.

A run is a results_P[_tag] directory holding mfsim.p0.lst (or mfsim.lst for a
serial run), found in the model directory or one level below it. Repeated runs
sit in sibling run_N directories; only partition counts every replicate
finished are kept, and of those the replicate with the middle total inner
iterations is selected. Iterations are summed over every time step and
solution, and memory over every rank of the selected replicate.

On the cluster, or anywhere the listings are:

  ./mf6_runs.py /projects/0/prjs0960/saltfingers3D --csv saltfingers3d.csv

From another machine, with an ssh key for Snellius; the script is sent over ssh
and run there, and the CSV is written locally to data/<model>.csv:

  ./mf6_runs.py /projects/0/prjs0960/saltfingers3D --remote
  ./mf6_runs.py /projects/0/prjs0960/bigsquare --remote --user <name>

Only the standard library is used, so this runs against the system python on the
cluster.
"""

import argparse
import pathlib as pl
import re
import shlex
import subprocess
import sys

ELAPSED = re.compile(r"Elapsed run time:(.*)", re.I)
UNITS = {"DAYS": 86400, "HOURS": 3600, "MINUTES": 60, "SECONDS": 1}
OUTER = re.compile(
    r"^\s*(\d+)\s+CALLS TO NUMERICAL SOLUTION IN TIME STEP\s+(\d+)"
    r"\s+STRESS PERIOD\s+(\d+)",
    re.I | re.M,
)
INNER = re.compile(r"^\s*(\d+)\s+TOTAL ITERATIONS", re.I | re.M)
PROFILE_RUN = re.compile(r"^\s*\[\s*[\d.]+%\]\s+Run:\s+([\d.]+)s", re.M)
PROFILE_LINEAR = re.compile(
    r"^\s*\[\s*[\d.]+%\]\s+Linear solve\s+:\s+([\d.]+)s", re.M
)
RESULTS = re.compile(r"^results_(\d+)p?(?:_(.+))?$")
MEMORY = re.compile(r"MEMORY MANAGER TOTAL STORAGE.*\bIN\s+([A-Z]+)", re.I)
MEMORY_TOTAL = re.compile(r"^\s*Total\s+([0-9.eE+-]+)\s*$")
SCRIPT_DIR = pl.Path(__file__).resolve().parent
DATADIR = SCRIPT_DIR / "data"
USER = "jhughes"
HOST = "snellius.surf.nl"
RANKLST = re.compile(r"^mfsim\.p(\d+)\.lst$")

# the memory manager picks the unit of its table from the magnitude
TO_GB = {
    "BYTES": 1.0 / 1024**3,
    "KILOBYTES": 1.0 / 1024**2,
    "MEGABYTES": 1.0 / 1024,
    "GIGABYTES": 1.0,
    "TERABYTES": 1024.0,
}

FIELDS = (
    "tag", "nprocs", "replicates", "selected", "elapsed", "run", "linear",
    "outer", "inner", "nsteps", "memory", "elapsed_min", "elapsed_max",
)


def hms(seconds):
    h, rem = divmod(int(round(seconds)), 3600)
    return f"{h:02d}:{rem // 60:02d}:{rem % 60:02d}"


def parse_elapsed(text):
    """Seconds from the elapsed run time line, or None if the run did not end.

    Components that are zero are left out of the line, so each value is paired
    with the unit that follows it.
    """
    m = ELAPSED.search(text)
    if m is None:
        return None
    t, prev = 0.0, None
    for tok in m.group(1).replace(",", " ").split():
        u = UNITS.get(tok.upper())
        if u is not None and prev is not None:
            t += prev * u
            prev = None
        else:
            try:
                prev = float(tok)
            except ValueError:
                prev = None
    return t


def parse_iterations(text):
    """(outer, inner, time steps), summed over every time step and solution."""
    calls = OUTER.findall(text)
    outer = sum(int(n) for n, _, _ in calls)
    inner = sum(int(n) for n in INNER.findall(text))
    nsteps = len({(sp, ts) for _, ts, sp in calls})
    return outer, inner, nsteps


def parse_profile(text):
    """(run, linear solve) seconds from the profiler, None when not written."""
    run = PROFILE_RUN.search(text)
    linear = PROFILE_LINEAR.search(text)
    return (
        float(run.group(1)) if run else None,
        float(linear.group(1)) if linear else None,
    )


def rank_memory(path):
    """Memory manager total, in gigabytes, from one listing, or None."""
    scale = None
    with open(path, errors="replace") as f:
        for line in f:
            if scale is None:
                m = MEMORY.search(line)
                if m:
                    scale = TO_GB.get(m.group(1).upper())
                    if scale is None:
                        raise ValueError(f"{path}: unknown units -- {line.strip()}")
                continue
            m = MEMORY_TOTAL.match(line)
            if m:
                return float(m.group(1)) * scale
    return None


def run_memory(rundir, nprocs):
    """Memory manager total over every rank of a run, in gigabytes.

    None unless a listing survives for each of the nprocs ranks.
    """
    paths = [p for p in rundir.glob("mfsim.p*.lst") if RANKLST.match(p.name)]
    if not paths:
        paths = [rundir / "mfsim.lst"]
    if len(paths) != nprocs:
        return None
    total = 0.0
    for p in paths:
        v = rank_memory(p) if p.is_file() else None
        if v is None:
            return None
        total += v
    return total


def listing(rundir):
    """The rank 0 listing of a run, or None."""
    for name in ("mfsim.p0.lst", "mfsim.lst"):
        path = rundir / name
        if path.is_file():
            return path
    return None


def read_run(rundir):
    """Timing and iterations of one finished run, or None."""
    path = listing(rundir)
    if path is None:
        return None
    text = path.read_text(errors="replace")
    elapsed = parse_elapsed(text)
    if elapsed is None:
        return None
    outer, inner, nsteps = parse_iterations(text)
    run, linear = parse_profile(text)
    return {
        "path": rundir,
        "elapsed": elapsed,
        "run": run,
        "linear": linear,
        "outer": outer,
        "inner": inner,
        "nsteps": nsteps,
    }


def results_dirs(parent):
    return sorted(
        d for d in parent.glob("results_*") if d.is_dir() and RESULTS.match(d.name)
    )


def replicates(root):
    """The results_P directories of each replicate under root.

    run_N directories are replicates; without them the results_P directories
    in root, or one level below it, are a single replicate.
    """
    runs = sorted(
        (d for d in root.glob("run_*") if d.is_dir()),
        key=lambda d: (len(d.name), d.name),
    )
    if runs:
        return [results_dirs(d) for d in runs]
    found = results_dirs(root)
    if not found:
        for d in sorted(root.iterdir()):
            if d.is_dir():
                found.extend(results_dirs(d))
    return [found]


def collect(root, quiet=False):
    """{tag: {nprocs: [run, ...]}} over every replicate under root.

    With more than one replicate, only partition counts every replicate
    finished are kept.
    """
    reps = replicates(root)
    runs = {}
    for dirs in reps:
        seen = {}
        for d in dirs:
            m = RESULTS.match(d.name)
            nprocs, tag = int(m.group(1)), m.group(2) or "default"
            if (tag, nprocs) in seen:
                if not quiet:
                    print(
                        f"  {d.relative_to(root)}: {nprocs} partitions already "
                        f"read from {seen[tag, nprocs].relative_to(root)}, skipped"
                    )
                continue
            r = read_run(d)
            if r is None:
                if not quiet:
                    print(f"  {d.relative_to(root)}: not finished, skipped")
                continue
            seen[tag, nprocs] = d
            runs.setdefault(tag, {}).setdefault(nprocs, []).append(r)
    if len(reps) > 1:
        for tag, byp in runs.items():
            missing = sorted(p for p in byp if len(byp[p]) < len(reps))
            for p in missing:
                del byp[p]
            if missing and not quiet:
                print(
                    f"  {tag}: {', '.join(str(p) for p in missing)} partitions "
                    f"not in all {len(reps)} replicates, dropped"
                )
    return runs


def select(replicates):
    """The replicate with the middle total inner iterations.

    Ties, which are usual when the partitioning is deterministic, fall back to
    the middle elapsed time; an even count takes the lower middle.
    """
    ordered = sorted(replicates, key=lambda r: (r["inner"], r["elapsed"]))
    return ordered[(len(ordered) - 1) // 2]


def memory(reps, selected, nprocs):
    """Memory of the selected replicate, else of one with every rank listed.

    Allocations depend only on the partitioning, so any complete replicate
    gives the same total; the others are read only when the selected one is
    incomplete, since reading every rank is slow.
    """
    for r in [selected] + [v for v in reps if v is not selected]:
        v = run_memory(r["path"], nprocs)
        if v is not None:
            return v
    return None


def summarize(root, quiet=False):
    """One row per tag and partition count, from the selected replicate."""
    rows = []
    for tag, byp in sorted(collect(root, quiet).items()):
        for nprocs in sorted(byp):
            reps = byp[nprocs]
            r = select(reps)
            times = [v["elapsed"] for v in reps]
            rows.append({
                "tag": tag,
                "nprocs": nprocs,
                "replicates": len(reps),
                "selected": str(r["path"].relative_to(root)),
                "elapsed": r["elapsed"],
                "run": r["run"],
                "linear": r["linear"],
                "outer": r["outer"],
                "inner": r["inner"],
                "nsteps": r["nsteps"],
                "memory": memory(reps, r, nprocs),
                "elapsed_min": min(times),
                "elapsed_max": max(times),
            })
    return rows


def write_csv(rows, path):
    import csv

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: "" if row[k] is None else row[k] for k in FIELDS})


def read_csv(path):
    import csv

    ints = ("nprocs", "replicates", "outer", "inner", "nsteps")
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            for k in FIELDS:
                if k in ("tag", "selected"):
                    continue
                # a CSV written before memory was a column reads as missing
                v = row.get(k, "")
                row[k] = None if v == "" else (int(v) if k in ints else float(v))
            rows.append(row)
    return rows


def model_name(source, resolve=True):
    """Lowercase model name from a run directory or CSV path.

    A directory named results is the model's own results directory, so its
    parent names the model. A remote path is not resolved.
    """
    if resolve:
        source = source.resolve()
    name = source.stem if source.suffix.lower() == ".csv" else source.name
    if name.lower() == "results":
        name = source.parent.name
    return name.lower()


def load(source, tag=None):
    """Rows of one tag, from a CSV or a run directory.

    The tag may be left out when the source has only one.
    """
    if source.suffix.lower() == ".csv":
        rows = read_csv(source)
    else:
        rows = summarize(source.resolve())
    tags = sorted({r["tag"] for r in rows})
    if not tags:
        raise SystemExit(f"no finished runs in {source}")
    if tag is None:
        if len(tags) > 1:
            raise SystemExit(f"{source} has tags {tags}, pick one with --tag")
        tag = tags[0]
    rows = [r for r in rows if r["tag"] == tag]
    if not rows:
        raise SystemExit(f"no runs tagged {tag} in {source}, have {tags}")
    return rows


def report(rows):
    """Speedup and solver work per tag, relative to the fewest partitions."""
    for tag in sorted({r["tag"] for r in rows}):
        runs = [r for r in rows if r["tag"] == tag]
        base = runs[0]
        print(f"\n{tag}, relative to {base['nprocs']} partitions\n")
        print(
            " parts  reps     elapsed     spread  speedup    eff"
            "    steps     outer       inner   s/inner  inner/base   memory GB"
        )
        for r in runs:
            speedup = base["elapsed"] / r["elapsed"]
            ideal = r["nprocs"] / base["nprocs"]
            spread = r["elapsed_max"] - r["elapsed_min"]
            print(
                f"{r['nprocs']:6d}  {r['replicates']:4d}  {hms(r['elapsed'])}"
                f"  {spread:8.1f}s  {speedup:7.2f}  {speedup / ideal * 100:5.1f}%"
                f"  {r['nsteps']:7d}  {r['outer']:8,}  {r['inner']:10,}"
                f"  {r['elapsed'] / r['inner']:8.4f}"
                f"  {r['inner'] / base['inner']:10.2f}"
                f"  {'?' if r['memory'] is None else format(r['memory'], ',.1f'):>10}"
            )
        if any(r["replicates"] > 1 for r in runs):
            print(
                "\n  spread is the range of elapsed time over the replicates; "
                "the row is\n  the replicate with the middle inner iterations"
            )


def remote(root, csv, user, host):
    """Run this script on host over ssh, writing its CSV to the local csv.

    The script is sent on stdin, the report comes back on stdout and the CSV
    on stderr, so nothing is written on the cluster.
    """
    cmd = f"python3 - {shlex.quote(str(root))} --csv /dev/stderr"
    proc = subprocess.run(
        ["ssh", f"{user}@{host}", cmd],
        input=pl.Path(__file__).read_bytes(),
        stderr=subprocess.PIPE,
    )
    text = proc.stderr.decode(errors="replace")
    if proc.returncode != 0 or not text.startswith(FIELDS[0]):
        sys.stderr.write(text)
        raise SystemExit(f"ssh {user}@{host} failed (exit {proc.returncode})")
    csv.write_text(text)
    print(f"\nwrote {csv}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "root", type=pl.Path, nargs="?", default=pl.Path.cwd(),
        help="model directory holding results_P, <model>_Pp/results_P, or "
        "run_N/results_P (default cwd)",
    )
    parser.add_argument(
        "--csv", type=pl.Path,
        help="also write the selected runs to this file (with --remote, "
        "default data/<model>.csv beside this script)",
    )
    parser.add_argument(
        "--remote", action="store_true",
        help="root is on the cluster; run there over ssh",
    )
    parser.add_argument(
        "--user", default=USER, help=f"cluster user name (default {USER})"
    )
    parser.add_argument(
        "--host", default=HOST, help=f"cluster login host (default {HOST})"
    )
    args = parser.parse_args()

    if args.remote:
        root = pl.PurePosixPath(args.root)
        csv = args.csv
        if csv is None:
            csv = DATADIR / f"{model_name(root, resolve=False)}.csv"
            csv.parent.mkdir(parents=True, exist_ok=True)
        remote(root, csv, args.user, args.host)
        return 0

    if not args.root.is_dir():
        raise SystemExit(f"no directory {args.root}")
    rows = summarize(args.root.resolve())
    if not rows:
        raise SystemExit(f"no finished runs under {args.root}")
    report(rows)
    if args.csv is not None:
        write_csv(rows, args.csv)
        # the remote run sends its CSV back on stderr
        if str(args.csv) != "/dev/stderr":
            print(f"\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
