import pandas as pd
import matplotlib.pyplot as plt
import os

def plot_training():
    path = "results/training_logs.csv"
    if not os.path.exists(path):
        print(f"WARNING: {path} not found.")
        return
        
    df = pd.read_csv(path)
    
    # We only plot RL performance evaluation metrics based on the updated CSV
    fig, axs = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("RL Agent Training Performance", fontsize=16, fontweight="bold")
    
    # 1. Cumulative Reward
    axs[0].plot(df["episode"], df["cumulative_reward"], color="green")
    axs[0].set_title("Total Reward per Episode")
    axs[0].set_xlabel("Episode")
    axs[0].set_ylabel("Reward")
    axs[0].grid(True, linestyle="--", alpha=0.5)
    
    # 2. Average Reward
    axs[1].plot(df["episode"], df["average_reward"], color="blue")
    axs[1].set_title("Average Step Reward")
    axs[1].set_xlabel("Episode")
    axs[1].set_ylabel("Reward")
    axs[1].grid(True, linestyle="--", alpha=0.5)
    
    # 3. Loss
    axs[2].plot(df["episode"], df["average_loss"], color="orange")
    axs[2].set_title("Agent Training Loss")
    axs[2].set_xlabel("Episode")
    axs[2].set_ylabel("MSE Loss")
    axs[2].grid(True, linestyle="--", alpha=0.5)
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig("results/training_performance.png", dpi=150)
    plt.close()
    
    print("plot_training.py execution complete. Check results/training_performance.png.")

if __name__ == "__main__":
    plot_training()
