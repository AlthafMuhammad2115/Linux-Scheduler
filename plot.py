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
    return df

A = load_csv("results/with_rl.csv")       # with RL agent
B = load_csv("results/without_rl.csv")    # baseline (nice=0)

# ===================== HELPER =====================

def plot_comparison(ax, A, B, col, ylabel, title, rolling=5, invert=False):
    """Plot a smoothed metric with rolling average for both conditions."""
    for df, label, color in [(A, "With RL", "#1f77b4"), (B, "Without RL", "#ff7f0e")]:
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


# ===================== FIGURE 1: THROUGHPUT vs TIME =====================
# Throughput = 1/latency  (hackbench tasks per second)

fig, ax = plt.subplots(figsize=(10, 5))
plot_comparison(ax, A, B, "throughput",
                ylabel="Throughput  (tasks / sec)",
                title="Throughput vs Time   [higher = better]")
plt.tight_layout()
plt.savefig("results/throughput_vs_time.png", dpi=150)
plt.close()
print("Saved results/throughput_vs_time.png")


# ===================== FIGURE 2: RESPONSIVENESS vs TIME =====================
# Responsiveness = 100 / (1 + wait_frac * 2)  — higher means less scheduling wait

fig, ax = plt.subplots(figsize=(10, 5))
plot_comparison(ax, A, B, "responsiveness",
                ylabel="Responsiveness Score  (0–100)",
                title="Responsiveness vs Time   [higher = better]")
plt.tight_layout()
plt.savefig("results/responsiveness_vs_time.png", dpi=150)
plt.close()
print("Saved results/responsiveness_vs_time.png")


# ===================== FIGURE 3: LATENCY vs TIME =====================

fig, ax = plt.subplots(figsize=(10, 5))
plot_comparison(ax, A, B, "latency",
                ylabel="hackbench Latency  (seconds)",
                title="Task Latency vs Time   [lower = better]")
plt.tight_layout()
plt.savefig("results/latency_vs_time.png", dpi=150)
plt.close()
print("Saved results/latency_vs_time.png")


# ===================== FIGURE 4: CPU NICE % vs TIME =====================
# cpu_nice rises when nice=+5 is applied; drops when nice=−5

fig, ax = plt.subplots(figsize=(10, 5))
plot_comparison(ax, A, B, "cpu_nice",
                ylabel="CPU Nice %  (niced-process share)",
                title="CPU Nice% vs Time   [reflects RL priority decisions]")
plt.tight_layout()
plt.savefig("results/cpu_nice_vs_time.png", dpi=150)
plt.close()
print("Saved results/cpu_nice_vs_time.png")


# ===================== FIGURE 5: SUMMARY DASHBOARD =====================

fig = plt.figure(figsize=(14, 10))
fig.suptitle("RL Scheduler — Evaluation Summary Dashboard", fontsize=14, fontweight="bold")
gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

metrics = [
    ("throughput",    "Tasks/sec",     "Throughput",       gs[0, 0]),
    ("responsiveness","Score (0-100)", "Responsiveness",   gs[0, 1]),
    ("latency",       "Seconds",       "Task Latency",     gs[1, 0]),
    ("cpu_nice",      "CPU %",         "CPU Nice %",       gs[1, 1]),
]

for col, ylabel, title, pos in metrics:
    ax = fig.add_subplot(pos)
    plot_comparison(ax, A, B, col, ylabel=ylabel, title=title)

plt.savefig("results/eval_dashboard.png", dpi=150)
plt.close()
print("Saved results/eval_dashboard.png")

print("\nDone! Check the /results folder.")
