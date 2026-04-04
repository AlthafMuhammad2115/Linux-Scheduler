import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os

# ===================== LOAD DATA =====================

def load_csv(path):
    if not os.path.exists(path):
        print(f"WARNING: {path} not found — skipping.")
        return None
    df = pd.read_csv(path)
    df["time"] = df["time"] - df["time"].iloc[0]   # normalize to 0
    # Add calculated efficiency manually for plotting
    df["mig_efficiency"] = df["mig_successes"] / df["mig_attempts"].replace(0, 1) * 100
    return df

A = load_csv("results/with_rl.csv")       # with RL agent
B = load_csv("results/without_rl.csv")    # baseline 

# ===================== HELPER =====================

def plot_comparison(ax, A, B, col, ylabel, title, rolling=5, invert=False):
    """Plot a smoothed metric with rolling average for both conditions."""
    for df, label, color in [(A, "With RL", "#1f77b4"), (B, "Baseline", "#ff7f0e")]:
        if df is None:
            continue
        y = df[col].rolling(rolling, min_periods=1).mean()
        if invert:
            y = -y
        ax.plot(df["time"], y, label=label, color=color, linewidth=1.8)
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)

# ===================== FIGURE 1: THROUGHPUT =====================

fig, ax = plt.subplots(figsize=(10, 5))
plot_comparison(ax, A, B, "throughput",
                ylabel="Throughput  (tasks / sec)",
                title="Throughput vs Time   [higher = better]")
plt.tight_layout()
plt.savefig("results/throughput_vs_time.png", dpi=150)
plt.close()

# ===================== FIGURE 2: LATENCY =====================

fig, ax = plt.subplots(figsize=(10, 5))
plot_comparison(ax, A, B, "latency",
                ylabel="Latency  (seconds)",
                title="Latency vs Time   [lower = better]")
plt.tight_layout()
plt.savefig("results/latency_vs_time.png", dpi=150)
plt.close()

# ===================== FIGURE 3: CPU VARIANCE =====================

fig, ax = plt.subplots(figsize=(10, 5))
plot_comparison(ax, A, B, "cpu_variance",
                ylabel="Total CPU Variance",
                title="CPU Load Variance vs Time   [lower = better balance]")
plt.tight_layout()
plt.savefig("results/cpu_variance_vs_time.png", dpi=150)
plt.close()

# ===================== FIGURE 4: MIGRATION COST =====================

fig, ax = plt.subplots(figsize=(10, 5))
plot_comparison(ax, A, B, "migration_cost",
                ylabel="migration_cost_ns",
                title="Scheduler Migration Cost vs Time")
plt.tight_layout()
plt.savefig("results/migration_cost_vs_time.png", dpi=150)
plt.close()

# ===================== FIGURE 5: SUMMARY DASHBOARD =====================

fig = plt.figure(figsize=(14, 10))
fig.suptitle("Learning EAS — Evaluation Summary Dashboard", fontsize=14, fontweight="bold")
gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

metrics = [
    ("throughput",    "Tasks/sec",     "Throughput [Higher is Better]",       gs[0, 0]),
    ("latency",       "Seconds",       "Latency [Lower is Better]",     gs[0, 1]),
    ("cpu_variance",  "Variance",      "CPU Variance [Lower is Better]",       gs[1, 0]),
    ("mig_efficiency","% Success",     "Migration Efficiency",       gs[1, 1]),
]

for col, ylabel, title, pos in metrics:
    ax = fig.add_subplot(pos)
    plot_comparison(ax, A, B, col, ylabel=ylabel, title=title)

plt.savefig("results/eval_dashboard.png", dpi=150)
plt.close()

print("plot.py execution complete. Check the /results folder.")
