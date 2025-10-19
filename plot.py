import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load CSV files
file1 = 'scheduler_metrics_RL_20250926_023230.csv'
file2 = 'scheduler_metrics_CFS_20250926_025150.csv'

df1 = pd.read_csv(file1)
df2 = pd.read_csv(file2)

# Add a column to identify the source CSV
df1['Source'] = 'Custom (RL)'
df2['Source'] = 'Traditional (CFS)'

# Convert timestamp to datetime for proper plotting
df1['timestamp'] = pd.to_datetime(df1['timestamp'])
df2['timestamp'] = pd.to_datetime(df2['timestamp'])

# --- FIX: Create an 'elapsed_time' column for each dataframe ---
# This normalizes the start time of both experiments to zero.
df1['elapsed_time'] = (df1['timestamp'] - df1['timestamp'].min()).dt.total_seconds()
df2['elapsed_time'] = (df2['timestamp'] - df2['timestamp'].min()).dt.total_seconds()

# Combine both dataframes
df = pd.concat([df1, df2])

# Plot response_time_s comparison using the new 'elapsed_time' column
plt.figure(figsize=(14, 6))
sns.lineplot(x='elapsed_time', y='response_time_s', hue='Source', data=df, marker='o')
plt.title('Response Time Comparison Over Time')
plt.xlabel('Elapsed Time (s)')
plt.ylabel('Response Time (s)')
plt.grid(True)
plt.tight_layout()
plt.savefig('response_time_comparison.png', dpi=300)
plt.show()

# Plot throughput comparison using the new 'elapsed_time' column
plt.figure(figsize=(14, 6))
sns.lineplot(x='elapsed_time', y='throughput', hue='Source', data=df, marker='o')
plt.title('Throughput Comparison Over Time')
plt.xlabel('Elapsed Time (s)')
plt.ylabel('Throughput (ops/sec)')
plt.grid(True)
plt.tight_layout()
plt.savefig('throughput_comparison.png', dpi=300)
plt.show()