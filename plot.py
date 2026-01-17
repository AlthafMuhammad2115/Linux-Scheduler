import pandas as pd, matplotlib.pyplot as plt

A = pd.read_csv("results/with_rl.csv")
B = pd.read_csv("results/without_rl.csv")

A["throughput"] = A["cpu_group"]
B["throughput"] = B["cpu_group"]

A["time"] = A["time"] - A["time"].iloc[0]
B["time"] = B["time"] - B["time"].iloc[0]

A["responsiveness"] = 1/(A["runqueue"]+1)
B["responsiveness"] = 1/(B["runqueue"]+1)

plt.figure()
plt.plot(A["time"],A["throughput"],label="With RL")
plt.plot(B["time"],B["throughput"],label="Without RL")
plt.legend(); plt.savefig("results/throughput_vs_time.png"); plt.close()

plt.figure()
plt.plot(A["time"],A["responsiveness"],label="With RL")
plt.plot(B["time"],B["responsiveness"],label="Without RL")
plt.legend(); plt.savefig("results/responsiveness_vs_time.png"); plt.close()
