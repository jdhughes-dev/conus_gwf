#!/usr/bin/env python
"""
LaTeX table of memory, iterations, and scaling for MODFLOW 6 parallel runs.

Writes the tabular of the manuscript's timing table, from the replicate
mf6_runs.py selects: memory, outer and total inner iterations, and the time,
speedup, and efficiency of the total simulation and the linear solution. Input
is a run directory or the CSV mf6_runs.py --csv writes.

  ./TableScaling.py data/conus_sweep.csv --tag disv   # tables/conus_sweep_disv.tex
  ./TableScaling.py data/saltfingers3d.csv            # tables/saltfingers3d.tex

The float, caption, label, and \\sisetup stay in the manuscript, which inputs
the file in place of its tabular. Only the standard library is used.
"""

import argparse
import pathlib as pl
import sys

from mf6_runs import load, model_name

SCRIPT_DIR = pl.Path(__file__).resolve().parent
TABLEDIR = SCRIPT_DIR.parent / "tables"
INDENT = "    "


def digits(values, decimals):
    """siunitx table-format for the widest of values."""
    width = 1
    for v in values:
        if v is not None:
            width = max(width, len(f"{abs(v):.{decimals}f}".split(".")[0]))
    return f"{width}.{decimals}"


def columns(rows, ref):
    """(group, header, table-format, cells) of each column.

    Memory and the linear solution are left out when no run reports them; the
    total simulation is the profiler Run total, else the elapsed run time.
    """
    base = next(r for r in rows if r["nprocs"] == ref)
    cols = [
        (None, "{Number of}", "{partitions}", [r["nprocs"] for r in rows], 0),
    ]
    if any(r["memory"] is not None for r in rows):
        cols.append(
            (None, "{Memory}", "{(GiB)}", [r["memory"] for r in rows], 1)
        )
    cols.append(("Iterations", "", "{Outer}", [r["outer"] for r in rows], 0))
    cols.append(("Iterations", "", "{Total}", [r["inner"] for r in rows], 0))

    groups = [("Total simulation", [r["run"] or r["elapsed"] for r in rows])]
    if all(r["linear"] is not None for r in rows):
        groups.append(("Linear solution", [r["linear"] for r in rows]))
    for name, times in groups:
        tref = times[rows.index(base)]
        speedup, efficiency = [], []
        for r, t in zip(rows, times):
            s = tref / t
            speedup.append(s)
            efficiency.append(100.0 * s / (r["nprocs"] / ref))
        cols.append((name, "", "{Time (s)}", times, 0))
        cols.append((name, "", "{$S_p$}", speedup, 2))
        cols.append((name, "", "{$E_p$ (\\%)}", efficiency, 1))
    return cols


def cell(v, decimals):
    return "{--}" if v is None else f"{v:.{decimals}f}"


def tabular(rows, ref):
    """The tabular environment, as lines."""
    cols = columns(rows, ref)
    specs = [f"S[table-format={digits(c[3], c[4])}]" for c in cols]
    lines = ["\\begin{tabular}{"]
    for i in range(0, len(specs), 2):
        lines.append(f"{INDENT}  " + " ".join(specs[i:i + 2]))
    lines.append(f"{INDENT}}}")
    lines.append(f"{INDENT}\\toprule")

    # first header row: ungrouped headers, then a multicolumn per group
    first, rules, i = [], [], 0
    while i < len(cols):
        group = cols[i][0]
        if group is None:
            first.append(cols[i][1])
            i += 1
            continue
        n = 0
        while i + n < len(cols) and cols[i + n][0] == group:
            n += 1
        first.append(f"\\multicolumn{{{n}}}{{c}}{{{group}}}")
        rules.append(f"\\cmidrule(lr){{{i + 1}-{i + n}}}")
        i += n
    lines.append(f"{INDENT}" + " & ".join(first) + " \\\\")
    lines.append(f"{INDENT}" + " ".join(rules))
    lines.append(f"{INDENT}" + " & ".join(c[2] for c in cols) + " \\\\")
    lines.append(f"{INDENT}\\midrule")

    # right-align each column so the source reads as a table
    text = [[cell(v, c[4]) for v in c[3]] for c in cols]
    widths = [max(len(t) for t in col) for col in text]
    for j in range(len(rows)):
        cells = [text[k][j].rjust(widths[k]) for k in range(len(cols))]
        lines.append(f"{INDENT}" + " & ".join(cells) + " \\\\")
    lines.append(f"{INDENT}\\bottomrule")
    lines.append("\\end{tabular}")
    return lines


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "source", type=pl.Path,
        help="run directory (results_P or run_N/results_P) or mf6_runs.py CSV",
    )
    parser.add_argument("--tag", help="results_P_<tag> variant to tabulate")
    parser.add_argument(
        "--ref", type=int,
        help="partitions speedup refers to (default the fewest)",
    )
    parser.add_argument(
        "--model",
        help="model name, the table is tables/<model>[_<tag>].tex "
        "(default the source name, lowercased)",
    )
    parser.add_argument(
        "--out", type=pl.Path,
        help="output file, a bare name goes in tables/ "
        "(default <model>.tex, or <model>_<tag>.tex with --tag)",
    )
    args = parser.parse_args()

    rows = load(args.source, args.tag)
    parts = [r["nprocs"] for r in rows]
    ref = parts[0] if args.ref is None else args.ref
    if ref not in parts:
        raise SystemExit(f"no run at {ref} partitions, have {parts}")

    model = args.model.lower() if args.model else model_name(args.source)
    out = args.out
    if out is None:
        out = pl.Path(f"{model}.tex" if args.tag is None
                      else f"{model}_{args.tag}.tex")
    if out.parent == pl.Path("."):
        out = TABLEDIR / out

    missing = [r["nprocs"] for r in rows if r["memory"] is None]
    if missing and len(missing) < len(rows):
        print(f"no memory for {missing} partitions, written as --")

    lines = tabular(rows, ref)
    print("\n".join(lines))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"% generated by scaling/TableScaling.py, p_ref = {ref}\n"
        + "\n".join(lines) + "\n"
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
