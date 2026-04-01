import pandas as pd
import matplotlib.pyplot as plt

A = pd.read_csv("results/with_rl.csv")
B = pd.read_csv("results/without_rl.csv")

# Normalize time
A["time"] = A["time"] - A["time"].iloc[0]
B["time"] = B["time"] - B["time"].iloc[0]

# Throughput (proxy)
A["throughput"] = A["cpu_group"]
B["throughput"] = B["cpu_group"]

# Responsiveness
A["responsiveness"] = 1 / (A["runqueue"] + 1)
B["responsiveness"] = 1 / (B["runqueue"] + 1)

# ---- FILTER FIRST 60 SECONDS ----
A_60 = A[A["time"] <= 300]
B_60 = B[B["time"] <= 300]

# ---- Throughput vs Time ----
plt.figure()
plt.plot(A_60["time"], A_60["throughput"], label="With RL")
plt.plot(B_60["time"], B_60["throughput"], label="Without RL")
plt.xlabel("Time (seconds)")
plt.ylabel("Throughput")
plt.title("Throughput vs Time")
plt.legend()
plt.savefig("results/throughput_vs_time.png")
plt.close()

# ---- Responsiveness vs Time ----
plt.figure()
plt.plot(A_60["time"], A_60["responsiveness"], label="With RL")
plt.plot(B_60["time"], B_60["responsiveness"], label="Without RL")
plt.xlabel("Time (seconds)")
plt.ylabel("Responsiveness")
plt.title("Responsiveness vs Time")
plt.legend()
plt.savefig("results/responsiveness_vs_time.png")
plt.close()
