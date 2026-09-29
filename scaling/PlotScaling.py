#!/usr/bin/env python
"""
Scaling figure, speedup and efficiency, for any set of MODFLOW 6 parallel runs.

Panel A is the total simulation and panel B the linear solution, from the
profiler Run and Linear solve totals of the replicate mf6_runs.py selects. A run
without the profiler has no linear solve time, and gets panel A alone at half
the width. Input is a local run directory or the CSV mf6_runs.py writes, so the
listings can be read on the cluster and the figure drawn elsewhere.

  ./PlotScaling.py data/saltfingers3d.csv
  ./PlotScaling.py data/conus_sweep.csv --tag disv
  ./PlotScaling.py data/bigsquare.csv --legend outside

Figures go in figures/scaling/<model>/, as scaling or scaling_<tag>.

Needs matplotlib and flopy (the conus environment).
"""

import argparse
import pathlib as pl

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

import flopy

from mf6_runs import load, model_name

SCRIPT_DIR = pl.Path(__file__).resolve().parent
FIGDIR = SCRIPT_DIR.parent / "figures" / "scaling"

# 17.15 cm, the two-column Groundwater width
FIGWIDTH = 6.75
FIGHEIGHT = 3.25
DPI = 600
FORMATS = ("pdf", "png")

# ps.fonttype is not in the flopy style sheets, EPS would carry Type 3 fonts
mpl.rcParams["ps.fonttype"] = 42

HEADINGS = ("Total simulation", "Linear solution")
SPEEDUP_COLOR = "black"
EFFICIENCY_COLOR = "#c1272d"
# legend anchors in panel A, inset from the corner so the title clears the
# efficiency axis; upper left sits below the model label
LEGEND_ANCHORS = {
    "lower right": (0.94, 0.04),
    "upper left": (0.04, 0.88),
    "upper right": (0.94, 0.96),
    "lower left": (0.04, 0.04),
}
IDEAL_COLOR = "0.55"


def timings(rows):
    """(partitions, total seconds, linear seconds) arrays.

    The profiler Run total is used for the simulation when it was written,
    else the elapsed run time.
    """
    parts = np.array([r["nprocs"] for r in rows])
    total = np.array([r["run"] or r["elapsed"] for r in rows], dtype=float)
    linear = np.array(
        [np.nan if r["linear"] is None else r["linear"] for r in rows]
    )
    return parts, total, linear


def scaling(parts, times, ref):
    """Speedup and efficiency, relative to ref partitions."""
    i = int(np.flatnonzero(parts == ref)[0])
    speedup = times[i] / times
    efficiency = 100.0 * speedup / (parts / ref)
    return speedup, efficiency


def pow2_ticks(lo, hi):
    """Powers of two spanning lo to hi."""
    return [2**k for k in range(int(np.floor(np.log2(lo))),
                                int(np.ceil(np.log2(hi))) + 1)]


def plot_panel(ax, parts, times, ref, heading, idx, ylim, efflim,
               left_label=True, right_label=True):
    """One panel: speedup on the left axis, efficiency on the right."""
    speedup, efficiency = scaling(parts, times, ref)
    ideal = parts / ref

    ax.plot(parts, ideal, color=IDEAL_COLOR, lw=1.0, ls="--",
            label="Ideal speedup")
    # the axes end on the first and last partition count, so the end markers
    # are drawn unclipped to keep them whole
    ax.plot(parts, speedup, color=SPEEDUP_COLOR, lw=1.0, marker="o", ms=4,
            mfc=SPEEDUP_COLOR, mec=SPEEDUP_COLOR, clip_on=False,
            label="Speedup")

    ax.set_xscale("log", base=2)
    ax.set_yscale("log", base=2)
    ax.set_xlim(parts[0], parts[-1])
    ax.set_ylim(*ylim)
    ax.set_xticks(parts)
    ax.set_xticklabels([f"{p}" for p in parts])
    yticks = [t for t in pow2_ticks(*ylim) if ylim[0] <= t <= ylim[1]]
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{t:g}" for t in yticks])
    ax.tick_params(axis="both", which="minor", length=0)

    flopy.plot.styles.xlabel(ax=ax, label="Number of partitions", fontsize=8)
    if left_label:
        flopy.plot.styles.ylabel(ax=ax, label="Speedup", fontsize=8)
    else:
        ax.tick_params(axis="y", labelleft=False)

    ax2 = ax.twinx()
    ax2.plot(parts, efficiency, color=EFFICIENCY_COLOR, lw=1.0, marker="s",
             ms=4, ls=":", mfc="none", mec=EFFICIENCY_COLOR, clip_on=False,
             label="Efficiency")
    ax2.set_ylim(0, efflim)
    ax2.set_yticks(np.arange(0, efflim + 1, 25))
    ax2.tick_params(axis="y", colors=EFFICIENCY_COLOR, labelsize=8)
    ax2.spines["right"].set_color(EFFICIENCY_COLOR)
    if right_label:
        flopy.plot.styles.ylabel(ax=ax2, label="Efficiency, in percent",
                                 fontsize=8, color=EFFICIENCY_COLOR)
    else:
        ax2.tick_params(axis="y", labelright=False)

    flopy.plot.styles.heading(ax=ax, idx=idx, heading=heading, fontsize=8)
    return ax2


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "source", type=pl.Path,
        help="run directory (results_P or run_N/results_P) or mf6_runs.py CSV",
    )
    parser.add_argument("--tag", help="results_P_<tag> variant to plot")
    parser.add_argument(
        "--ref", type=int,
        help="partitions speedup refers to (default the fewest)",
    )
    parser.add_argument(
        "--model",
        help="model name, figures go in figures/scaling/<model> "
        "(default the source name, lowercased)",
    )
    parser.add_argument(
        "--out", type=pl.Path,
        help="output basename, a bare name goes in the model directory "
        "(default scaling, or scaling_<tag> with --tag)",
    )
    parser.add_argument(
        "--label",
        help="text in the upper left of panel A (default the model name "
        "without _sweep, with the tag when --tag is given)",
    )
    parser.add_argument(
        "--legend", choices=sorted(LEGEND_ANCHORS) + ["outside"],
        default="lower right",
        help="legend corner in panel A, or outside above the panels "
        "(default lower right)",
    )
    parser.add_argument(
        "--dpi", type=int, default=DPI, help=f"raster resolution ({DPI})"
    )
    args = parser.parse_args()

    parts, total, linear = timings(load(args.source, args.tag))
    ref = parts[0] if args.ref is None else args.ref
    if ref not in parts:
        raise SystemExit(f"no run at {ref} partitions, have {list(parts)}")

    model = args.model.lower() if args.model else model_name(args.source)
    out = args.out
    if out is None:
        out = pl.Path("scaling" if args.tag is None else f"scaling_{args.tag}")
    if out.parent == pl.Path("."):
        out = FIGDIR / model / out

    series = [total] if np.isnan(linear).any() else [total, linear]
    if len(series) == 1:
        print("linear solve time missing for some runs, total panel only")

    # shared limits so the panels read against each other
    speedups, effs = [], []
    for t in series:
        s, e = scaling(parts, t, ref)
        speedups.extend(s)
        effs.extend(e)
    ideal = parts / ref
    lo = min(min(speedups), ideal.min()) / 1.25
    hi = max(max(speedups), ideal.max()) * 1.4
    efflim = 25 * np.ceil(max(max(effs), 100) * 1.05 / 25)

    with flopy.plot.styles.USGSPlot():
        fig, axs = plt.subplots(
            # one panel, when there is no linear solve time, is half the width
            ncols=len(series),
            figsize=(FIGWIDTH * len(series) / 2, FIGHEIGHT),
            constrained_layout=True, squeeze=False,
        )
        axs = axs[0]
        twins = [
            plot_panel(axs[i], parts, t, ref, HEADINGS[i], i, (lo, hi),
                       efflim, left_label=(i == 0),
                       right_label=(i == len(series) - 1))
            for i, t in enumerate(series)
        ]

        # a <model>_sweep directory holds the partition sweep of that model
        label = args.label
        if label is None:
            label = model.removesuffix("_sweep")
            if args.tag not in (None, "default"):
                label = f"{label} {args.tag}"
        # offset in points from the corner so the label clears the inward
        # ticks on the left and top spines whatever the panel width
        pad = mpl.rcParams["ytick.major.size"] + 3.0
        flopy.plot.styles.add_annotation(
            ax=axs[0], text=label, xy=(0.0, 1.0), xytext=(pad, -pad),
            xycoords="axes fraction", textcoords="offset points",
            ha="left", va="top", bold=False, italic=True, fontsize=8,
        )

        handles, labels = axs[0].get_legend_handles_labels()
        h2, l2 = twins[0].get_legend_handles_labels()
        if args.legend == "outside":
            # one row above the panels, for data that leaves no corner clear
            fig.legend(
                handles + h2, labels + l2, loc="outside upper center",
                ncol=3, fontsize=7, frameon=False,
            )
        else:
            flopy.plot.styles.graph_legend(
                ax=axs[0], handles=handles + h2, labels=labels + l2,
                loc=args.legend, bbox_to_anchor=LEGEND_ANCHORS[args.legend],
                fontsize=7, frameon=False, borderaxespad=0,
            )

        out.parent.mkdir(parents=True, exist_ok=True)
        for ext in FORMATS:
            fig.savefig(out.with_suffix(f".{ext}"), dpi=args.dpi)
            print(f"wrote {out.with_suffix(f'.{ext}')}")
        plt.close(fig)


if __name__ == "__main__":
    main()
