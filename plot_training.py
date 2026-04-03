import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os

log_path = "results/training_logs.csv"

if not os.path.exists(log_path):
    print(f"Error: {log_path} not found. Please run main.py with TRAIN_MODE=True first.")
    exit(1)

df = pd.read_csv(log_path)
episodes = df["episode"]

# ===================== HELPER =====================

def save_plot(x, y, title, xlabel, ylabel, filename, color="blue"):
    plt.figure(figsize=(9, 4))
    plt.plot(x, y, marker='o', markersize=3, linestyle='-', color=color)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(f"results/{filename}", dpi=150)
    plt.close()
    print(f"Saved {filename}")

print("Generating Training RL Metrics Plots...")

# 1. Cumulative Reward
save_plot(episodes, df["cumulative_reward"],
          "Cumulative Reward per Episode", "Episode", "Cumulative Reward",
          "train_cumulative_reward.png", color="green")

# 2. Average Reward
save_plot(episodes, df["average_reward"],
          "Average Reward per Episode", "Episode", "Average Reward",
          "train_average_reward.png", color="orange")

# 3. Loss Curve
save_plot(episodes, df["average_loss"],
          "Average Loss vs Episode", "Episode", "Loss (MSE)",
          "train_loss_curve.png", color="red")

# 4. Throughput per Episode (new)
if "avg_throughput" in df.columns:
    save_plot(episodes, df["avg_throughput"],
              "Average Throughput per Episode", "Episode", "Tasks / sec",
              "train_throughput.png", color="steelblue")

# 5. Latency per Episode (new)
if "avg_latency" in df.columns:
    save_plot(episodes, df["avg_latency"],
              "Average hackbench Latency per Episode", "Episode", "Latency (s)",
              "train_latency.png", color="purple")

# 6. Responsiveness per Episode (new)
if "avg_responsiveness" in df.columns:
    save_plot(episodes, df["avg_responsiveness"],
              "Average Responsiveness per Episode", "Episode", "Score (0-100)",
              "train_responsiveness.png", color="teal")

# 7. Convergence: Reward + Epsilon dual axis
fig, ax1 = plt.subplots(figsize=(9, 4))
color = 'tab:orange'
ax1.set_xlabel('Episode')
ax1.set_ylabel('Average Reward', color=color)
ax1.plot(episodes, df["average_reward"], color=color, marker='o', markersize=3, label="Reward")
ax1.tick_params(axis='y', labelcolor=color)

ax2 = ax1.twinx()
color = 'tab:blue'
ax2.set_ylabel('Epsilon (Exploration Rate)', color=color)
ax2.plot(episodes, df["epsilon"], color=color, linestyle='--', marker='x', markersize=3, label="Epsilon")
ax2.tick_params(axis='y', labelcolor=color)

fig.tight_layout()
plt.title("Convergence Behavior: Reward vs Epsilon Decay")
plt.savefig("results/train_convergence.png", dpi=150)
plt.close()
print("Saved train_convergence.png")

# 8. Training Dashboard (throughput + latency + responsiveness + reward)
if all(c in df.columns for c in ["avg_throughput", "avg_latency", "avg_responsiveness"]):
    fig = plt.figure(figsize=(14, 8))
    fig.suptitle("Training Progress Dashboard", fontsize=13, fontweight="bold")
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

    plots = [
        ("average_reward",    "Reward",       "Average Reward",       gs[0, 0], "orange"),
        ("avg_throughput",    "Tasks/sec",    "Throughput",           gs[0, 1], "steelblue"),
        ("avg_latency",       "Seconds",      "hackbench Latency",    gs[1, 0], "purple"),
        ("avg_responsiveness","Score (0-100)","Responsiveness",       gs[1, 1], "teal"),
    ]

    for col, ylabel, title, pos, color in plots:
        ax = fig.add_subplot(pos)
        ax.plot(episodes, df[col], marker='o', markersize=3, color=color)
        ax.set_title(title)
        ax.set_xlabel("Episode")
        ax.set_ylabel(ylabel)
        ax.grid(True, linestyle="--", alpha=0.5)

    plt.savefig("results/train_dashboard.png", dpi=150)
    plt.close()
    print("Saved train_dashboard.png")

print("\nDone! Check the /results folder for plots.")
