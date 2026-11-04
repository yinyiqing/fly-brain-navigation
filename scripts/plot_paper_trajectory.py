#!/usr/bin/env python3
"""Draw the prespecified seed 701 trajectories at a readable paper size."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    data = pd.read_csv(ROOT / "examples/validation-20261104/demo_trajectories.csv")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(5.8, 2.8))
    for ax, noise in zip(axes, [5, 15]):
        trial = data[data.noise_deg == noise].sort_values("step")
        outbound = trial[trial.phase == "outbound"]
        back = pd.concat([outbound.tail(1), trial[trial.phase != "outbound"]])
        ax.plot(outbound.x, outbound.y, "--", color="#8d969b", lw=1, label="Outbound")
        ax.plot(back.x, back.y, color="#33866b", lw=1.4, label="Return + search")
        ax.add_patch(Circle((0, 0), 1, color="#33866b", alpha=.15))
        ax.scatter([0], [0], marker="*", s=55, color="#34464d", zorder=4)
        ax.scatter([trial.iloc[-1].x], [trial.iloc[-1].y], s=20,
                   color="#33866b" if noise == 5 else "#b65151", zorder=4)
        ax.set(xlim=(-6.5, 10), ylim=(-2, 15), xlabel="x", ylabel="y",
               title=f"Observation {noise}°: " + ("reached" if noise == 5 else "failed"))
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=.15)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.tight_layout(rect=(0, .12, 1, 1))
    destination = ROOT / "reports/assets/paper_trajectory.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=220)
    plt.close(fig)
    print(destination)


if __name__ == "__main__":
    main()
