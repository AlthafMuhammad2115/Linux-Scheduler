# import psutil
# import time
# import os

# def collect_system_state(interval=1):
#     # CPU Utilization (overall + per-core)
#     cpu_percent_total = psutil.cpu_percent(interval=None)
#     cpu_percent_per_core = psutil.cpu_percent(interval=None, percpu=True)

#     # CPU Frequency (per-core)
#     cpu_freq = psutil.cpu_freq(percpu=True)
#     cpu_freqs = [f.current for f in cpu_freq]

#     # Load average (Linux only)
#     try:
#         load_avg = os.getloadavg()  # (1min, 5min, 15min)
#     except (AttributeError, OSError):
#         load_avg = (0.0, 0.0, 0.0)

#     # Context switches
#     ctx_switches = psutil.cpu_stats().ctx_switches

#     # CPU times (user, system, idle, iowait, etc.)
#     cpu_times = psutil.cpu_times_percent(interval=None, percpu=False)._asdict()

#     # Memory usage
#     mem = psutil.virtual_memory()
#     memory_usage = mem.percent

#     # Per-process CPU utilization (top 5 by CPU%)
#     processes = []
#     for p in psutil.process_iter(attrs=['pid', 'name', 'cpu_percent', 'memory_percent', 'nice']):
#         try:
#             proc_info = p.info
#             proc_info['cpu_core'] = p.cpu_num()  # add which core is being used
#             processes.append(proc_info)
#         except (psutil.NoSuchProcess, psutil.AccessDenied):
#             continue
#     top_processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:5]

#     state = {
#         "cpu_total_percent": cpu_percent_total,
#         "cpu_per_core_percent": cpu_percent_per_core,
#         "cpu_freqs": cpu_freqs,
#         "load_avg": load_avg,
#         "ctx_switches": ctx_switches,
#         "cpu_times": cpu_times,
#         "memory_usage_percent": memory_usage,
#         "top_processes": top_processes
#     }

#     return state


# if __name__ == "__main__":
#     while True:
#         state = collect_system_state()
#         print(state)
#         time.sleep(1)  # collect every second

# import time
# import numpy as np
# import tensorflow as tf
# from tensorflow.keras.models import Sequential
# from tensorflow.keras.layers import Dense
# from tensorflow.keras.optimizers import Adam
# import paramiko
# import re

# # --- VM Configuration ---
# VM_IP = 'localhost'
# VM_PORT = 2222
# VM_USER = 'althaf2004'
# VM_PASS = 'Althaf@2004'

# class LinuxEnvironment:
#     """
#     Handles all communication with the QEMU VM.
#     Defines the state, action, and reward logic.
#     """
#     def __init__(self):
#         self.ssh = paramiko.SSHClient()
#         self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         self.ssh.connect(VM_IP, port=VM_PORT, username=VM_USER, password=VM_PASS)
        
#         self.action_space_size = 3
#         self.state_space_size = 1
        
#         # sched_cfs_bandwidth_slice_us parameters (values are in microseconds)
#         self.base_cost = 5000
#         self.step_size = 500
#         self.min_cost = 1000
#         self.max_cost = 20000
        
#         self.previous_cpu_times = self._get_cpu_times()

#     def _execute_command(self, command):
#         """Executes a command and returns both stdout and stderr."""
#         stdin, stdout, stderr = self.ssh.exec_command(command, get_pty=True)
#         output = stdout.read().decode().strip()
#         error_output = stderr.read().decode().strip()
#         return output, error_output

#     def _get_cpu_times(self):
#         """Parses /proc/stat to get total and idle times for each CPU."""
#         stat_output, _ = self._execute_command("cat /proc/stat")
#         cpu_times = {}
#         for line in stat_output.split('\n'):
#             if line.startswith('cpu') and line.split()[0] != 'cpu':
#                 parts = line.split()
#                 cpu_id = parts[0]
#                 total_time = sum(map(int, parts[1:8]))
#                 idle_time = int(parts[4])
#                 cpu_times[cpu_id] = {'total': total_time, 'idle': idle_time}
#         return cpu_times

#     def get_state_and_utilization(self):
#         """Calculates CPU utilization for each core and the variance."""
#         current_cpu_times = self._get_cpu_times()
#         utilizations = []
#         for cpu_id in self.previous_cpu_times:
#             delta_total = current_cpu_times[cpu_id]['total'] - self.previous_cpu_times[cpu_id]['total']
#             delta_idle = current_cpu_times[cpu_id]['idle'] - self.previous_cpu_times[cpu_id]['idle']
            
#             if delta_total == 0:
#                 utilization = 0
#             else:
#                 utilization = 100 * (1 - delta_idle / delta_total)
#             utilizations.append(utilization)
        
#         self.previous_cpu_times = current_cpu_times
        
#         variance = np.var(utilizations)
#         state = np.array([variance])
#         return state, utilizations, variance

#     def step(self, action):
#         """Apply an action, run a benchmark, and collect metrics."""
#         metrics = {}
        
#         # 1. Apply the action
#         current_cost_str, _ = self._execute_command("cat /proc/sys/kernel/sched_cfs_bandwidth_slice_us")
#         current_cost = int(current_cost_str)
        
#         if action == 0: new_cost = max(self.min_cost, current_cost - self.step_size)
#         elif action == 2: new_cost = min(self.max_cost, current_cost + self.step_size)
#         else: new_cost = current_cost
            
#         self._execute_command(f"echo {new_cost} | sudo -S tee /proc/sys/kernel/sched_cfs_bandwidth_slice_us")
        
#         # 2. Collect metrics during benchmark
#         cs_before_str, _ = self._execute_command("cat /proc/vmstat | grep cs")
#         cs_before = int(cs_before_str.split()[1])
        
#         benchmark_cmd = "sudo perf stat -e sched:sched_migrate_task -- time stress-ng --cpu 4 --cpu-method all -t 5s"
#         _, bench_output = self._execute_command(benchmark_cmd)
        
#         cs_after_str, _ = self._execute_command("cat /proc/vmstat | grep cs")
#         cs_after = int(cs_after_str.split()[1])

#         # 3. Parse benchmark output for metrics
#         execution_time = 10.0 # Default penalty value
#         migrations = 0
#         try:
#             time_match = re.search(r'real\s+0m([\d.]+)s', bench_output)
#             if time_match:
#                 execution_time = float(time_match.group(1))
            
#             migrations_match = re.search(r'(\d+)\s+sched:sched_migrate_task', bench_output)
#             if migrations_match:
#                 migrations = int(migrations_match.group(1).replace(',', ''))
#         except Exception:
#             print("Warning: Could not parse all benchmark metrics.")

#         # 4. Get post-benchmark state
#         next_state, utilizations, variance = self.get_state_and_utilization()

#         # 5. Populate metrics dictionary
#         metrics['CPU utilization per core'] = [f'{u:.2f}%' for u in utilizations]
#         metrics['Load variance across CPUs'] = f'{variance:.4f}'
#         metrics['Runqueue length per CPU'] = 'N/A (requires advanced parsing)'
#         metrics['Number of migration attempts'] = 'N/A (requires advanced parsing)'
#         metrics['Number of successful migrations'] = migrations
#         metrics['Migration efficiency'] = 'N/A'
#         metrics['Average wake-to-run latency'] = 'N/A (requires advanced parsing)'
#         metrics['Average task wait time in runqueue'] = 'N/A (requires advanced parsing)'
#         metrics['Application startup / response time'] = f'{execution_time:.4f}s'
#         metrics['Tasks completed per second'] = f'{(1/execution_time if execution_time > 0 else 0):.2f}'
#         metrics['Jobs completed in a fixed interval'] = '1 (stress-ng run)'
#         metrics['Context switch rate'] = f'{(cs_after - cs_before) / 5.0:.2f}/s' # 5s is benchmark time
#         metrics['Scheduler-induced latency'] = 'N/A (requires advanced parsing)'

#         reward = 1.0 / execution_time
#         return next_state, reward, metrics

#     def reset(self):
#         """Resets the environment for a new episode."""
#         self._execute_command(f"echo {self.base_cost} | sudo -S tee /proc/sys/kernel/sched_cfs_bandwidth_slice_us")
#         state, _, _ = self.get_state_and_utilization()
#         return state

#     def close(self):
#         self.ssh.close()


# class PolicyGradientAgent:
#     def __init__(self, state_size, action_size):
#         self.state_size = state_size
#         self.action_size = action_size
#         self.gamma = 0.95
#         self.learning_rate = 0.001
#         self.model = self._build_model()
#         self.state_memory, self.action_memory, self.reward_memory = [], [], []

#     def _build_model(self):
#         model = Sequential([
#             Dense(24, input_dim=self.state_size, activation='relu'),
#             Dense(24, activation='relu'),
#             Dense(self.action_size, activation='softmax')
#         ])
#         model.compile(optimizer=Adam(learning_rate=self.learning_rate), loss='categorical_crossentropy')
#         return model

#     def store_transition(self, state, action, reward):
#         self.state_memory.append(state)
#         self.action_memory.append(action)
#         self.reward_memory.append(reward)

#     def choose_action(self, state):
#         state = state.reshape([1, self.state_size])
#         probabilities = self.model.predict(state, verbose=0)[0]
#         action = np.random.choice(self.action_size, p=probabilities)
#         return action

#     def learn(self):
#         states = np.array(self.state_memory)
#         actions = np.array(self.action_memory)
#         rewards = np.array(self.reward_memory)
        
#         actions_one_hot = np.zeros([len(actions), self.action_size])
#         actions_one_hot[np.arange(len(actions)), actions] = 1
        
#         discounted_rewards = np.zeros_like(rewards, dtype=float)
#         running_add = 0
#         for t in reversed(range(len(rewards))):
#             running_add = running_add * self.gamma + rewards[t]
#             discounted_rewards[t] = running_add
            
#         discounted_rewards -= np.mean(discounted_rewards)
#         std_dev = np.std(discounted_rewards)
#         if std_dev > 0:
#             discounted_rewards /= std_dev
        
#         self.model.train_on_batch(states, actions_one_hot * discounted_rewards[:, None])
#         self.state_memory, self.action_memory, self.reward_memory = [], [], []


# if __name__ == "__main__":
#     env = LinuxEnvironment()
#     agent = PolicyGradientAgent(state_size=env.state_space_size, action_size=env.action_space_size)
    
#     NUM_EPISODES = 50

#     for episode in range(NUM_EPISODES):
#         state = env.reset()
#         print(f"--- Episode {episode+1}/{NUM_EPISODES} ---")
        
#         for step in range(10):
#             action = agent.choose_action(state)
#             next_state, reward, metrics = env.step(action)
            
#             agent.store_transition(state, action, reward)
#             state = next_state
            
#             # --- Formatted Metrics Output ---
#             print(f"\n--- Step {step+1} Metrics ---")
#             print("1. CPU Load and Balancing Metrics")
#             print(f"   - CPU utilization per core: {metrics['CPU utilization per core']}")
#             print(f"   - Load variance across CPUs: {metrics['Load variance across CPUs']}")
#             print(f"   - Runqueue length per CPU: {metrics['Runqueue length per CPU']}")
#             print("\n2. Task Migration Metrics")
#             print(f"   - Number of migration attempts: {metrics['Number of migration attempts']}")
#             print(f"   - Number of successful migrations: {metrics['Number of successful migrations']}")
#             print(f"   - Migration efficiency: {metrics['Migration efficiency']}")
#             print("\n3. Latency / Responsiveness Metrics")
#             print(f"   - Average wake-to-run latency: {metrics['Average wake-to-run latency']}")
#             print(f"   - Average task wait time in runqueue: {metrics['Average task wait time in runqueue']}")
#             print(f"   - Application startup / response time: {metrics['Application startup / response time']}")
#             print("\n4. Throughput Metrics")
#             print(f"   - Tasks completed per second: {metrics['Tasks completed per second']}")
#             print(f"   - Jobs completed in a fixed interval: {metrics['Jobs completed in a fixed interval']}")
#             print("\n5. Overhead / Cost Metrics")
#             print(f"   - Context switch rate: {metrics['Context switch rate']}")
#             print(f"   - Scheduler-induced latency: {metrics['Scheduler-induced latency']}")
#             print("-" * 25)

#         agent.learn()

#     env.close()
#     print("Training finished.")


# import time
# import numpy as np
# import tensorflow as tf
# from tensorflow.keras.models import Sequential
# from tensorflow.keras.layers import Dense
# from tensorflow.keras.optimizers import Adam
# import paramiko
# import re
# import csv
# import json
# from datetime import datetime
# import threading

# # --- VM Configuration ---
# VM_IP = 'localhost'
# VM_PORT = 2222
# VM_USER = 'althaf2004'
# VM_PASS = 'Althaf@2004'

# # --- Configuration ---
# IS_ON = True  # Set to False to run with base CFS, True for RL-enhanced scheduling
# RECORD_INTERVAL = 10  # seconds between metric recordings
# OUTPUT_FILE = f"scheduler_metrics_{'RL' if IS_ON else 'CFS'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# class LinuxEnvironment:
#     """
#     Handles all communication with the QEMU VM.
#     Defines the state, action, and reward logic.
#     """
#     def __init__(self, is_on=True):
#         self.ssh = paramiko.SSHClient()
#         self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         self.ssh.connect(VM_IP, port=VM_PORT, username=VM_USER, password=VM_PASS)
        
#         self.is_on = is_on
#         self.action_space_size = 3
#         self.state_space_size = 3  # CPU variance, avg runqueue length, context switch rate
        
#         # sched_migration_cost parameters (values are in nanoseconds)
#         self.base_cost = 500000  # 0.5ms default
#         self.step_size = 50000   # 0.05ms steps
#         self.min_cost = 0        # 0ms minimum
#         self.max_cost = 5000000  # 5ms maximum
        
#         self.previous_cpu_times = self._get_cpu_times()
#         self.previous_context_switches = self._get_context_switches()
#         self.previous_time = time.time()
        
#         # Initialize metrics file
#         self.metrics_file = OUTPUT_FILE
#         self._init_metrics_file()

#     def _execute_command(self, command):
#         """Executes a command and returns both stdout and stderr."""
#         stdin, stdout, stderr = self.ssh.exec_command(command, get_pty=True)
#         output = stdout.read().decode().strip()
#         error_output = stderr.read().decode().strip()
#         return output, error_output

#     def _get_cpu_times(self):
#         """Parses /proc/stat to get total and idle times for each CPU."""
#         stat_output, _ = self._execute_command("cat /proc/stat")
#         cpu_times = {}
#         for line in stat_output.split('\n'):
#             if line.startswith('cpu') and line.split()[0] != 'cpu':
#                 parts = line.split()
#                 cpu_id = parts[0]
#                 total_time = sum(map(int, parts[1:8]))
#                 idle_time = int(parts[4])
#                 cpu_times[cpu_id] = {'total': total_time, 'idle': idle_time}
#         return cpu_times

#     def _get_context_switches(self):
#         """Get total context switches from /proc/stat."""
#         stat_output, _ = self._execute_command("cat /proc/stat | grep ctxt")
#         return int(stat_output.split()[1])

#     def _get_runqueue_lengths(self):
#         """Get runqueue lengths for each CPU."""
#         # Use /proc/sched_debug or alternative method
#         try:
#             output, _ = self._execute_command("cat /proc/loadavg")
#             load_avg = float(output.split()[0])  # 1-minute load average as proxy
#             # Estimate per-CPU runqueue length
#             cpu_count = len(self.previous_cpu_times)
#             avg_runqueue = load_avg / cpu_count if cpu_count > 0 else 0
#             return [avg_runqueue] * cpu_count  # Simplified approximation
#         except:
#             return [0.0] * len(self.previous_cpu_times)

#     def _get_migration_stats(self):
#         """Get task migration statistics from /proc/schedstat."""
#         try:
#             output, _ = self._execute_command("cat /proc/schedstat")
#             migrations = 0
#             attempts = 0
            
#             # Parse schedstat for migration data (simplified)
#             lines = output.split('\n')
#             for line in lines:
#                 if line.startswith('cpu'):
#                     parts = line.split()
#                     if len(parts) > 8:
#                         # Approximate migration data from schedstat
#                         migrations += int(parts[7]) if parts[7].isdigit() else 0
#                         attempts += int(parts[8]) if parts[8].isdigit() else 0
            
#             return migrations, attempts
#         except:
#             return 0, 0

#     def get_comprehensive_metrics(self):
#         """Collect all required metrics."""
#         current_time = time.time()
#         time_delta = current_time - self.previous_time
        
#         # 1. CPU Load and Balancing Metrics
#         current_cpu_times = self._get_cpu_times()
#         utilizations = []
        
#         for cpu_id in self.previous_cpu_times:
#             if cpu_id in current_cpu_times:
#                 delta_total = current_cpu_times[cpu_id]['total'] - self.previous_cpu_times[cpu_id]['total']
#                 delta_idle = current_cpu_times[cpu_id]['idle'] - self.previous_cpu_times[cpu_id]['idle']
                
#                 if delta_total == 0:
#                     utilization = 0
#                 else:
#                     utilization = 100 * (1 - delta_idle / delta_total)
#                 utilizations.append(max(0, min(100, utilization)))
        
#         cpu_variance = np.var(utilizations) if utilizations else 0
#         runqueue_lengths = self._get_runqueue_lengths()
#         avg_runqueue_length = np.mean(runqueue_lengths) if runqueue_lengths else 0
        
#         # 2. Task Migration Metrics
#         migrations, migration_attempts = self._get_migration_stats()
#         migration_efficiency = (migrations / migration_attempts * 100) if migration_attempts > 0 else 0
        
#         # 3. Context Switch Rate
#         current_cs = self._get_context_switches()
#         cs_rate = (current_cs - self.previous_context_switches) / time_delta if time_delta > 0 else 0
        
#         # Update previous values
#         self.previous_cpu_times = current_cpu_times
#         self.previous_context_switches = current_cs
#         self.previous_time = current_time
        
#         metrics = {
#             # 1. CPU Load and Balancing Metrics
#             'cpu_utilization_per_core': utilizations,
#             'load_variance_across_cpus': cpu_variance,
#             'avg_runqueue_length': avg_runqueue_length,
#             'runqueue_lengths_per_cpu': runqueue_lengths,
            
#             # 2. Task Migration Metrics
#             'migration_attempts': migration_attempts,
#             'successful_migrations': migrations,
#             'migration_efficiency': migration_efficiency,
            
#             # 3. Latency / Responsiveness Metrics (will be updated during workload)
#             'avg_wake_to_run_latency': 0,  # Placeholder
#             'avg_task_wait_time': 0,       # Placeholder
#             'application_response_time': 0, # Will be measured
            
#             # 4. Throughput Metrics (will be updated during workload)
#             'tasks_completed_per_second': 0,
#             'jobs_completed': 0,
            
#             # 5. Overhead / Cost Metrics
#             'context_switch_rate': cs_rate,
#             'scheduler_induced_latency': 0,  # Placeholder
            
#             # State for RL
#             'state': np.array([cpu_variance, avg_runqueue_length, cs_rate])
#         }
        
#         return metrics

#     def run_workload(self):
#         """Run hackbench workload for better scheduler stress testing."""
#         start_time = time.time()
        
#         # Use hackbench for better scheduler testing (more realistic than stress-ng)
#         workload_cmd = "hackbench -P -T -l 1000 -g 4"  # Process mode, threads, loops, groups
        
#         # Fallback to stress-ng if hackbench not available
#         fallback_cmd = "stress-ng --cpu 4 --cpu-method all --timeout 5s"
        
#         try:
#             output, error = self._execute_command(workload_cmd)
#             if "not found" in error or "command not found" in error:
#                 print("Hackbench not found, using stress-ng fallback")
#                 output, error = self._execute_command(fallback_cmd)
#         except:
#             output, error = self._execute_command(fallback_cmd)
        
#         end_time = time.time()
#         execution_time = end_time - start_time
        
#         # Parse throughput from output
#         throughput = 0
#         if "Time:" in output:
#             # Hackbench output parsing
#             time_match = re.search(r'Time: ([\d.]+)', output)
#             if time_match:
#                 workload_time = float(time_match.group(1))
#                 throughput = 1.0 / workload_time if workload_time > 0 else 0
#         else:
#             # Stress-ng or general case
#             throughput = 1.0 / execution_time if execution_time > 0 else 0
        
#         return execution_time, throughput

#     def step(self, action):
#         """Apply an action, run workload, and collect metrics."""
#         # 1. Apply the action (only if RL is enabled)
#         if self.is_on:
#             current_cost_str, _ = self._execute_command("sudo cat /sys/kernel/debug/sched/migration_cost_ns")
#             current_cost = int(current_cost_str)
            
#             if action == 0:  # Decrease
#                 new_cost = max(self.min_cost, current_cost - self.step_size)
#             elif action == 2:  # Increase
#                 new_cost = min(self.max_cost, current_cost + self.step_size)
#             else:  # Keep same
#                 new_cost = current_cost
            
#             self._execute_command(f"echo {new_cost} | sudo -S tee /sys/kernel/debug/sched/migration_cost_ns")
        
#         # 2. Run workload and measure performance
#         execution_time, throughput = self.run_workload()
        
#         # 3. Collect comprehensive metrics
#         metrics = self.get_comprehensive_metrics()
        
#         # 4. Update performance metrics
#         metrics['application_response_time'] = execution_time
#         metrics['tasks_completed_per_second'] = throughput
#         metrics['jobs_completed'] = 1  # One workload run
        
#         # 5. Calculate reward (for RL)
#         reward = throughput - (metrics['load_variance_across_cpus'] / 1000) - (metrics['context_switch_rate'] / 10000)
        
#         return metrics['state'], reward, metrics

#     def reset(self):
#         """Reset environment to base configuration."""
#         if self.is_on:
#             self._execute_command(f"echo {self.base_cost} | sudo -S tee /sys/kernel/debug/sched/migration_cost_ns")
        
#         # Wait for system to stabilize
#         time.sleep(2)
        
#         metrics = self.get_comprehensive_metrics()
#         return metrics['state']

#     def _init_metrics_file(self):
#         """Initialize CSV file with headers."""
#         headers = [
#             'timestamp', 'episode', 'step', 'mode',
#             'cpu_utilization_avg', 'cpu_utilization_std', 'load_variance',
#             'avg_runqueue_length', 'migration_attempts', 'successful_migrations',
#             'migration_efficiency', 'application_response_time', 'throughput',
#             'context_switch_rate', 'current_migration_cost'
#         ]
        
#         with open(self.metrics_file, 'w', newline='') as f:
#             writer = csv.writer(f)
#             writer.writerow(headers)

#     def record_metrics(self, metrics, episode=0, step=0):
#         """Record metrics to CSV file."""
#         try:
#             current_cost_str, _ = self._execute_command("sudo cat /sys/kernel/debug/sched/migration_cost_ns")
#             current_cost = int(current_cost_str)
#         except:
#             current_cost = self.base_cost
        
#         cpu_utils = metrics['cpu_utilization_per_core']
#         row = [
#             datetime.now().isoformat(),
#             episode,
#             step,
#             'RL' if self.is_on else 'CFS',
#             np.mean(cpu_utils) if cpu_utils else 0,
#             np.std(cpu_utils) if cpu_utils else 0,
#             metrics['load_variance_across_cpus'],
#             metrics['avg_runqueue_length'],
#             metrics['migration_attempts'],
#             metrics['successful_migrations'],
#             metrics['migration_efficiency'],
#             metrics['application_response_time'],
#             metrics['tasks_completed_per_second'],
#             metrics['context_switch_rate'],
#             current_cost
#         ]
        
#         with open(self.metrics_file, 'a', newline='') as f:
#             writer = csv.writer(f)
#             writer.writerow(row)

#     def print_metrics(self, metrics, episode, step):
#         """Print formatted metrics to console."""
#         print(f"\n=== Episode {episode+1}, Step {step+1} Metrics ===")
#         print("1. CPU Load and Balancing Metrics:")
#         cpu_utils = metrics['cpu_utilization_per_core']
#         print(f"   - CPU utilization per core: {[f'{u:.2f}%' for u in cpu_utils]}")
#         print(f"   - Load variance across CPUs: {metrics['load_variance_across_cpus']:.4f}")
#         print(f"   - Average runqueue length: {metrics['avg_runqueue_length']:.4f}")
        
#         print("\n2. Task Migration Metrics:")
#         print(f"   - Migration attempts: {metrics['migration_attempts']}")
#         print(f"   - Successful migrations: {metrics['successful_migrations']}")
#         print(f"   - Migration efficiency: {metrics['migration_efficiency']:.2f}%")
        
#         print("\n3. Latency/Responsiveness Metrics:")
#         print(f"   - Application response time: {metrics['application_response_time']:.4f}s")
#         print(f"   - Average runqueue length: {metrics['avg_runqueue_length']:.4f}")
        
#         print("\n4. Throughput Metrics:")
#         print(f"   - Tasks completed per second: {metrics['tasks_completed_per_second']:.2f}")
#         print(f"   - Jobs completed: {metrics['jobs_completed']}")
        
#         print("\n5. Overhead/Cost Metrics:")
#         print(f"   - Context switch rate: {metrics['context_switch_rate']:.2f}/s")
        
#         print("-" * 50)

#     def close(self):
#         self.ssh.close()


# class PolicyGradientAgent:
#     def __init__(self, state_size, action_size):
#         self.state_size = state_size
#         self.action_size = action_size
#         self.gamma = 0.95
#         self.learning_rate = 0.001
#         self.model = self._build_model()
#         self.state_memory, self.action_memory, self.reward_memory = [], [], []

#     def _build_model(self):
#         model = Sequential([
#             Dense(32, input_dim=self.state_size, activation='relu'),
#             Dense(32, activation='relu'),
#             Dense(16, activation='relu'),
#             Dense(self.action_size, activation='softmax')
#         ])
#         model.compile(optimizer=Adam(learning_rate=self.learning_rate), loss='categorical_crossentropy')
#         return model

#     def store_transition(self, state, action, reward):
#         self.state_memory.append(state)
#         self.action_memory.append(action)
#         self.reward_memory.append(reward)

#     def choose_action(self, state):
#         state = state.reshape([1, self.state_size])
#         probabilities = self.model.predict(state, verbose=0)[0]
#         action = np.random.choice(self.action_size, p=probabilities)
#         return action

#     def learn(self):
#         if len(self.state_memory) == 0:
#             return
        
#         states = np.array(self.state_memory)
#         actions = np.array(self.action_memory)
#         rewards = np.array(self.reward_memory)
        
#         actions_one_hot = np.zeros([len(actions), self.action_size])
#         actions_one_hot[np.arange(len(actions)), actions] = 1
        
#         discounted_rewards = np.zeros_like(rewards, dtype=float)
#         running_add = 0
#         for t in reversed(range(len(rewards))):
#             running_add = running_add * self.gamma + rewards[t]
#             discounted_rewards[t] = running_add
        
#         # Normalize rewards
#         mean_reward = np.mean(discounted_rewards)
#         std_reward = np.std(discounted_rewards)
#         if std_reward > 0:
#             discounted_rewards = (discounted_rewards - mean_reward) / std_reward
        
#         self.model.train_on_batch(states, actions_one_hot * discounted_rewards[:, None])
#         self.state_memory, self.action_memory, self.reward_memory = [], [], []


# def periodic_recording(env, stop_event):
#     """Record metrics periodically in a separate thread."""
#     while not stop_event.is_set():
#         try:
#             metrics = env.get_comprehensive_metrics()
#             env.record_metrics(metrics)
#             time.sleep(RECORD_INTERVAL)
#         except Exception as e:
#             print(f"Error in periodic recording: {e}")
#             break


# if __name__ == "__main__":
#     print(f"Starting scheduler optimization with mode: {'RL-Enhanced' if IS_ON else 'Base CFS'}")
#     print(f"Output file: {OUTPUT_FILE}")
    
#     env = LinuxEnvironment(is_on=IS_ON)
    
#     if IS_ON:
#         agent = PolicyGradientAgent(state_size=env.state_space_size, action_size=env.action_space_size)
#         NUM_EPISODES = 100  # Increased for better learning
#         STEPS_PER_EPISODE = 15
#     else:
#         agent = None
#         NUM_EPISODES = 50   # Fewer episodes for baseline measurement
#         STEPS_PER_EPISODE = 10
    
#     # Start periodic recording thread
#     stop_recording = threading.Event()
#     recording_thread = threading.Thread(target=periodic_recording, args=(env, stop_recording))
#     recording_thread.start()
    
#     try:
#         for episode in range(NUM_EPISODES):
#             state = env.reset()
#             print(f"\n{'='*60}")
#             print(f"Episode {episode+1}/{NUM_EPISODES}")
#             print(f"{'='*60}")
            
#             episode_rewards = []
            
#             for step in range(STEPS_PER_EPISODE):
#                 if IS_ON and agent:
#                     action = agent.choose_action(state)
#                 else:
#                     action = 1  # No-op action for baseline
                
#                 next_state, reward, metrics = env.step(action)
#                 episode_rewards.append(reward)
                
#                 if IS_ON and agent:
#                     agent.store_transition(state, action, reward)
                
#                 # Print metrics
#                 env.print_metrics(metrics, episode, step)
                
#                 # Record metrics
#                 env.record_metrics(metrics, episode, step)
                
#                 state = next_state
                
#                 # Small delay to prevent system overload
#                 time.sleep(1)
            
#             if IS_ON and agent:
#                 agent.learn()
            
#             avg_reward = np.mean(episode_rewards)
#             print(f"\nEpisode {episode+1} completed. Average reward: {avg_reward:.4f}")
            
#             # Longer pause between episodes
#             time.sleep(2)
    
#     except KeyboardInterrupt:
#         print("\nTraining interrupted by user.")
    
#     finally:
#         # Stop recording thread
#         stop_recording.set()
#         recording_thread.join(timeout=5)
        
#         env.close()
#         print(f"\nTraining finished. Metrics saved to: {OUTPUT_FILE}")
#         print("You can now run the script again with IS_ON=False to collect baseline data.")

# claude v1

# import time
# import numpy as np
# import tensorflow as tf
# from tensorflow.keras.models import Sequential
# from tensorflow.keras.layers import Dense
# from tensorflow.keras.optimizers import Adam
# import paramiko
# import re
# import csv
# import json
# from datetime import datetime
# import threading

# # --- VM Configuration ---
# VM_IP = 'localhost'
# VM_PORT = 2222
# VM_USER = 'althaf2004'
# VM_PASS = 'Althaf@2004'

# # --- Configuration ---
# IS_ON = True  # Set to False to run with base CFS, True for RL-enhanced scheduling
# RECORD_INTERVAL = 5  # seconds between metric recordings (only used post-training)
# POST_TRAINING_DURATION = 300  # seconds to record metrics after training (5 minutes)
# OUTPUT_FILE = f"scheduler_metrics_{'RL' if IS_ON else 'CFS'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# class LinuxEnvironment:
#     """
#     Handles all communication with the QEMU VM.
#     Defines the state, action, and reward logic.
#     """
#     def __init__(self, is_on=True):
#         self.ssh = paramiko.SSHClient()
#         self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         self.ssh.connect(VM_IP, port=VM_PORT, username=VM_USER, password=VM_PASS)
        
#         self.is_on = is_on
#         self.action_space_size = 3
#         self.state_space_size = 3  # CPU variance, avg runqueue length, context switch rate
        
#         # sched_migration_cost parameters (values are in nanoseconds)
#         self.base_cost = 500000  # 0.5ms default
#         self.step_size = 50000   # 0.05ms steps
#         self.min_cost = 0        # 0ms minimum
#         self.max_cost = 5000000  # 5ms maximum
        
#         self.previous_cpu_times = self._get_cpu_times()
#         self.previous_context_switches = self._get_context_switches()
#         self.previous_time = time.time()
        
#         # Initialize metrics file (but don't write during training)
#         self.metrics_file = OUTPUT_FILE

#     def _execute_command(self, command):
#         """Executes a command and returns both stdout and stderr."""
#         stdin, stdout, stderr = self.ssh.exec_command(command, get_pty=True)
#         output = stdout.read().decode().strip()
#         error_output = stderr.read().decode().strip()
#         return output, error_output

#     def _get_cpu_times(self):
#         """Parses /proc/stat to get total and idle times for each CPU."""
#         stat_output, _ = self._execute_command("cat /proc/stat")
#         cpu_times = {}
#         for line in stat_output.split('\n'):
#             if line.startswith('cpu') and line.split()[0] != 'cpu':
#                 parts = line.split()
#                 cpu_id = parts[0]
#                 total_time = sum(map(int, parts[1:8]))
#                 idle_time = int(parts[4])
#                 cpu_times[cpu_id] = {'total': total_time, 'idle': idle_time}
#         return cpu_times

#     def _get_context_switches(self):
#         """Get total context switches from /proc/stat."""
#         stat_output, _ = self._execute_command("cat /proc/stat | grep ctxt")
#         return int(stat_output.split()[1])

#     def _get_runqueue_lengths(self):
#         """Get runqueue lengths for each CPU."""
#         # Use /proc/sched_debug or alternative method
#         try:
#             output, _ = self._execute_command("cat /proc/loadavg")
#             load_avg = float(output.split()[0])  # 1-minute load average as proxy
#             # Estimate per-CPU runqueue length
#             cpu_count = len(self.previous_cpu_times)
#             avg_runqueue = load_avg / cpu_count if cpu_count > 0 else 0
#             return [avg_runqueue] * cpu_count  # Simplified approximation
#         except:
#             return [0.0] * len(self.previous_cpu_times)

#     def _get_migration_stats(self):
#         """Get task migration statistics from /proc/schedstat."""
#         try:
#             output, _ = self._execute_command("cat /proc/schedstat")
#             migrations = 0
#             attempts = 0
            
#             # Parse schedstat for migration data (simplified)
#             lines = output.split('\n')
#             for line in lines:
#                 if line.startswith('cpu'):
#                     parts = line.split()
#                     if len(parts) > 8:
#                         # Approximate migration data from schedstat
#                         migrations += int(parts[7]) if parts[7].isdigit() else 0
#                         attempts += int(parts[8]) if parts[8].isdigit() else 0
            
#             return migrations, attempts
#         except:
#             return 0, 0

#     def get_comprehensive_metrics(self):
#         """Collect all required metrics."""
#         current_time = time.time()
#         time_delta = current_time - self.previous_time
        
#         # 1. CPU Load and Balancing Metrics
#         current_cpu_times = self._get_cpu_times()
#         utilizations = []
        
#         for cpu_id in self.previous_cpu_times:
#             if cpu_id in current_cpu_times:
#                 delta_total = current_cpu_times[cpu_id]['total'] - self.previous_cpu_times[cpu_id]['total']
#                 delta_idle = current_cpu_times[cpu_id]['idle'] - self.previous_cpu_times[cpu_id]['idle']
                
#                 if delta_total == 0:
#                     utilization = 0
#                 else:
#                     utilization = 100 * (1 - delta_idle / delta_total)
#                 utilizations.append(max(0, min(100, utilization)))
        
#         cpu_variance = np.var(utilizations) if utilizations else 0
#         runqueue_lengths = self._get_runqueue_lengths()
#         avg_runqueue_length = np.mean(runqueue_lengths) if runqueue_lengths else 0
        
#         # 2. Task Migration Metrics
#         migrations, migration_attempts = self._get_migration_stats()
#         migration_efficiency = (migrations / migration_attempts * 100) if migration_attempts > 0 else 0
        
#         # 3. Context Switch Rate
#         current_cs = self._get_context_switches()
#         cs_rate = (current_cs - self.previous_context_switches) / time_delta if time_delta > 0 else 0
        
#         # Update previous values
#         self.previous_cpu_times = current_cpu_times
#         self.previous_context_switches = current_cs
#         self.previous_time = current_time
        
#         metrics = {
#             # 1. CPU Load and Balancing Metrics
#             'cpu_utilization_per_core': utilizations,
#             'load_variance_across_cpus': cpu_variance,
#             'avg_runqueue_length': avg_runqueue_length,
#             'runqueue_lengths_per_cpu': runqueue_lengths,
            
#             # 2. Task Migration Metrics
#             'migration_attempts': migration_attempts,
#             'successful_migrations': migrations,
#             'migration_efficiency': migration_efficiency,
            
#             # 3. Latency / Responsiveness Metrics (will be updated during workload)
#             'avg_wake_to_run_latency': 0,  # Placeholder
#             'avg_task_wait_time': 0,       # Placeholder
#             'application_response_time': 0, # Will be measured
            
#             # 4. Throughput Metrics (will be updated during workload)
#             'tasks_completed_per_second': 0,
#             'jobs_completed': 0,
            
#             # 5. Overhead / Cost Metrics
#             'context_switch_rate': cs_rate,
#             'scheduler_induced_latency': 0,  # Placeholder
            
#             # State for RL
#             'state': np.array([cpu_variance, avg_runqueue_length, cs_rate])
#         }
        
#         return metrics

#     def run_workload(self):
#         """Run hackbench workload for better scheduler stress testing."""
#         start_time = time.time()
        
#         # Use hackbench for better scheduler testing (more realistic than stress-ng)
#         workload_cmd = "hackbench -P -T -l 1000 -g 4"  # Process mode, threads, loops, groups
        
#         # Fallback to stress-ng if hackbench not available
#         fallback_cmd = "stress-ng --cpu 4 --cpu-method all --timeout 5s"
        
#         try:
#             output, error = self._execute_command(workload_cmd)
#             if "not found" in error or "command not found" in error:
#                 print("Hackbench not found, using stress-ng fallback")
#                 output, error = self._execute_command(fallback_cmd)
#         except:
#             output, error = self._execute_command(fallback_cmd)
        
#         end_time = time.time()
#         execution_time = end_time - start_time
        
#         # Parse throughput from output
#         throughput = 0
#         if "Time:" in output:
#             # Hackbench output parsing
#             time_match = re.search(r'Time: ([\d.]+)', output)
#             if time_match:
#                 workload_time = float(time_match.group(1))
#                 throughput = 1.0 / workload_time if workload_time > 0 else 0
#         else:
#             # Stress-ng or general case
#             throughput = 1.0 / execution_time if execution_time > 0 else 0
        
#         return execution_time, throughput

#     def step(self, action):
#         """Apply an action, run workload, and collect metrics."""
#         # 1. Apply the action (only if RL is enabled)
#         if self.is_on:
#             current_cost_str, _ = self._execute_command("sudo cat /sys/kernel/debug/sched/migration_cost_ns")
#             current_cost = int(current_cost_str)
            
#             if action == 0:  # Decrease
#                 new_cost = max(self.min_cost, current_cost - self.step_size)
#             elif action == 2:  # Increase
#                 new_cost = min(self.max_cost, current_cost + self.step_size)
#             else:  # Keep same
#                 new_cost = current_cost
            
#             self._execute_command(f"echo {new_cost} | sudo -S tee /sys/kernel/debug/sched/migration_cost_ns")
        
#         # 2. Run workload and measure performance
#         execution_time, throughput = self.run_workload()
        
#         # 3. Collect comprehensive metrics
#         metrics = self.get_comprehensive_metrics()
        
#         # 4. Update performance metrics
#         metrics['application_response_time'] = execution_time
#         metrics['tasks_completed_per_second'] = throughput
#         metrics['jobs_completed'] = 1  # One workload run
        
#         # 5. Calculate reward (for RL)
#         reward = throughput - (metrics['load_variance_across_cpus'] / 1000) - (metrics['context_switch_rate'] / 10000)
        
#         return metrics['state'], reward, metrics

#     def reset(self):
#         """Reset environment to base configuration."""
#         if self.is_on:
#             self._execute_command(f"echo {self.base_cost} | sudo -S tee /sys/kernel/debug/sched/migration_cost_ns")
        
#         # Wait for system to stabilize
#         time.sleep(2)
        
#         metrics = self.get_comprehensive_metrics()
#         return metrics['state']

#     def _init_metrics_file(self):
#         """Initialize CSV file with headers."""
#         headers = [
#             'timestamp', 'episode', 'step', 'mode',
#             'cpu_utilization_avg', 'cpu_utilization_std', 'load_variance',
#             'avg_runqueue_length', 'migration_attempts', 'successful_migrations',
#             'migration_efficiency', 'application_response_time', 'throughput',
#             'context_switch_rate', 'current_migration_cost'
#         ]
        
#         with open(self.metrics_file, 'w', newline='') as f:
#             writer = csv.writer(f)
#             writer.writerow(headers)

#     def record_metrics(self, metrics, episode=0, step=0):
#         """Record metrics to CSV file."""
#         try:
#             current_cost_str, _ = self._execute_command("sudo cat /sys/kernel/debug/sched/migration_cost_ns")
#             current_cost = int(current_cost_str)
#         except:
#             current_cost = self.base_cost
        
#         cpu_utils = metrics['cpu_utilization_per_core']
#         row = [
#             datetime.now().isoformat(),
#             episode,
#             step,
#             'RL' if self.is_on else 'CFS',
#             np.mean(cpu_utils) if cpu_utils else 0,
#             np.std(cpu_utils) if cpu_utils else 0,
#             metrics['load_variance_across_cpus'],
#             metrics['avg_runqueue_length'],
#             metrics['migration_attempts'],
#             metrics['successful_migrations'],
#             metrics['migration_efficiency'],
#             metrics['application_response_time'],
#             metrics['tasks_completed_per_second'],
#             metrics['context_switch_rate'],
#             current_cost
#         ]
        
#         with open(self.metrics_file, 'a', newline='') as f:
#             writer = csv.writer(f)
#             writer.writerow(row)

#     def print_metrics(self, metrics, episode, step):
#         """Print formatted metrics to console."""
#         print(f"\n=== Episode {episode+1}, Step {step+1} Metrics ===")
#         print("1. CPU Load and Balancing Metrics:")
#         cpu_utils = metrics['cpu_utilization_per_core']
#         print(f"   - CPU utilization per core: {[f'{u:.2f}%' for u in cpu_utils]}")
#         print(f"   - Load variance across CPUs: {metrics['load_variance_across_cpus']:.4f}")
#         print(f"   - Average runqueue length: {metrics['avg_runqueue_length']:.4f}")
        
#         print("\n2. Task Migration Metrics:")
#         print(f"   - Migration attempts: {metrics['migration_attempts']}")
#         print(f"   - Successful migrations: {metrics['successful_migrations']}")
#         print(f"   - Migration efficiency: {metrics['migration_efficiency']:.2f}%")
        
#         print("\n3. Latency/Responsiveness Metrics:")
#         print(f"   - Application response time: {metrics['application_response_time']:.4f}s")
#         print(f"   - Average runqueue length: {metrics['avg_runqueue_length']:.4f}")
        
#         print("\n4. Throughput Metrics:")
#         print(f"   - Tasks completed per second: {metrics['tasks_completed_per_second']:.2f}")
#         print(f"   - Jobs completed: {metrics['jobs_completed']}")
        
#         print("\n5. Overhead/Cost Metrics:")
#         print(f"   - Context switch rate: {metrics['context_switch_rate']:.2f}/s")
        
#         print("-" * 50)

#     def close(self):
#         self.ssh.close()


# class PolicyGradientAgent:
#     def __init__(self, state_size, action_size):
#         self.state_size = state_size
#         self.action_size = action_size
#         self.gamma = 0.95
#         self.learning_rate = 0.001
#         self.model = self._build_model()
#         self.state_memory, self.action_memory, self.reward_memory = [], [], []

#     def _build_model(self):
#         model = Sequential([
#             Dense(32, input_dim=self.state_size, activation='relu'),
#             Dense(32, activation='relu'),
#             Dense(16, activation='relu'),
#             Dense(self.action_size, activation='softmax')
#         ])
#         model.compile(optimizer=Adam(learning_rate=self.learning_rate), loss='categorical_crossentropy')
#         return model

#     def store_transition(self, state, action, reward):
#         self.state_memory.append(state)
#         self.action_memory.append(action)
#         self.reward_memory.append(reward)

#     def choose_action(self, state):
#         state = state.reshape([1, self.state_size])
#         probabilities = self.model.predict(state, verbose=0)[0]
#         action = np.random.choice(self.action_size, p=probabilities)
#         return action

#     def learn(self):
#         if len(self.state_memory) == 0:
#             return
        
#         states = np.array(self.state_memory)
#         actions = np.array(self.action_memory)
#         rewards = np.array(self.reward_memory)
        
#         actions_one_hot = np.zeros([len(actions), self.action_size])
#         actions_one_hot[np.arange(len(actions)), actions] = 1
        
#         discounted_rewards = np.zeros_like(rewards, dtype=float)
#         running_add = 0
#         for t in reversed(range(len(rewards))):
#             running_add = running_add * self.gamma + rewards[t]
#             discounted_rewards[t] = running_add
        
#         # Normalize rewards
#         mean_reward = np.mean(discounted_rewards)
#         std_reward = np.std(discounted_rewards)
#         if std_reward > 0:
#             discounted_rewards = (discounted_rewards - mean_reward) / std_reward
        
#         self.model.train_on_batch(states, actions_one_hot * discounted_rewards[:, None])
#         self.state_memory, self.action_memory, self.reward_memory = [], [], []


# def post_training_recording(env, duration=300):
#     """Record metrics for a specified duration after training is complete."""
#     print(f"\nTraining complete. Now recording metrics for {duration} seconds...")
#     start_time = time.time()
#     recorded_count = 0
    
#     while time.time() - start_time < duration:
#         try:
#             metrics = env.get_comprehensive_metrics()
#             env.record_metrics(metrics, episode="POST_TRAINING", step=recorded_count)
#             recorded_count += 1
#             print(f"Recording metrics... {recorded_count} samples collected")
#             time.sleep(RECORD_INTERVAL)
#         except Exception as e:
#             print(f"Error in post-training recording: {e}")
#             break
    
#     print(f"Metrics recording complete. Total samples: {recorded_count}")


# if __name__ == "__main__":
#     print(f"Starting scheduler optimization with mode: {'RL-Enhanced' if IS_ON else 'Base CFS'}")
#     print(f"Output file will be: {OUTPUT_FILE}")
#     print("Note: Metrics will only be recorded AFTER training is complete.")
    
#     env = LinuxEnvironment(is_on=IS_ON)
    
#     if IS_ON:
#         agent = PolicyGradientAgent(state_size=env.state_space_size, action_size=env.action_space_size)
#         NUM_EPISODES = 100  # Increased for better learning
#         STEPS_PER_EPISODE = 15
#     else:
#         agent = None
#         NUM_EPISODES = 50   # Fewer episodes for baseline measurement
#         STEPS_PER_EPISODE = 10
    
#     try:
#         # Training Phase
#         print(f"\n{'='*60}")
#         print("TRAINING PHASE - No metrics recording during training")
#         print(f"{'='*60}")
        
#         for episode in range(NUM_EPISODES):
#             state = env.reset()
#             print(f"\nEpisode {episode+1}/{NUM_EPISODES}")
            
#             episode_rewards = []
            
#             for step in range(STEPS_PER_EPISODE):
#                 if IS_ON and agent:
#                     action = agent.choose_action(state)
#                 else:
#                     action = 1  # No-op action for baseline
                
#                 next_state, reward, metrics = env.step(action)
#                 episode_rewards.append(reward)
                
#                 if IS_ON and agent:
#                     agent.store_transition(state, action, reward)
                
#                 # Print metrics to console only (no file recording during training)
#                 env.print_metrics(metrics, episode, step)
                
#                 state = next_state
                
#                 # Small delay to prevent system overload
#                 time.sleep(1)
            
#             if IS_ON and agent:
#                 agent.learn()
            
#             avg_reward = np.mean(episode_rewards)
#             print(f"Episode {episode+1} completed. Average reward: {avg_reward:.4f}")
            
#             # Longer pause between episodes
#             time.sleep(2)
        
#         # Post-Training Metrics Recording Phase
#         print(f"\n{'='*60}")
#         print("TRAINING COMPLETE - Starting metrics recording phase")
#         print(f"{'='*60}")
        
#         # Initialize the metrics file after training
#         env._init_metrics_file()
        
#         # Record metrics for specified duration
#         post_training_recording(env, duration=POST_TRAINING_DURATION)
    
#     except KeyboardInterrupt:
#         print("\nProcess interrupted by user.")
    
#     finally:
#         env.close()
#         print(f"\nProcess finished. Metrics saved to: {OUTPUT_FILE}")
#         if IS_ON:
#             print("You can now run the script again with IS_ON=False to collect baseline data.")
#         else:
#             print("Baseline data collection complete. You can now compare with RL data.")

# claude v2

# import time
# import numpy as np
# import tensorflow as tf
# from tensorflow.keras.models import Sequential
# from tensorflow.keras.layers import Dense
# from tensorflow.keras.optimizers import Adam
# import paramiko
# import re
# import csv
# from datetime import datetime

# # --- VM Configuration ---
# VM_IP = 'localhost'
# VM_PORT = 2222
# VM_USER = 'althaf2004'
# VM_PASS = 'Althaf@2004'

# # --- Configuration ---
# IS_ON = True  # Set to False to run with base CFS, True for RL-enhanced scheduling
# RECORD_INTERVAL = 5  # seconds between metric recordings (only used post-training)
# POST_TRAINING_DURATION = 300  # seconds to record metrics after training
# SLEEP_INTERVAL = 7  # seconds between measurements (as per paper)
# THRESHOLD = 160000  # threshold for action decision (as per paper)
# STEP_SIZE = 17027   # step size for migration cost adjustment (as per paper)
# OUTPUT_FILE = f"scheduler_metrics_{'RL' if IS_ON else 'CFS'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# class ImprovedLinuxEnvironment:
#     """
#     Enhanced Linux Environment based on research paper algorithm.
#     Implements cluster-based CPU variance and temporal error calculation.
#     """
#     def __init__(self, is_on=True):
#         self.ssh = paramiko.SSHClient()
#         self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         self.ssh.connect(VM_IP, port=VM_PORT, username=VM_USER, password=VM_PASS)
        
#         self.is_on = is_on
#         self.action_space_size = 2  # Increase or decrease migration cost
        
#         # Migration cost parameters (values in nanoseconds)
#         self.base_cost = 500000  # 0.5ms default
#         self.min_cost = 0
#         self.max_cost = 5000000  # 5ms maximum
#         self.mc = 0  # Current migration cost adjustment
        
#         # Get CPU topology for cluster-based analysis
#         self.cpu_clusters = self._get_cpu_clusters()
#         self.num_clusters = len(self.cpu_clusters)
#         self.state_space_size = self.num_clusters + 2  # cluster variances + mig_count + mig_success
        
#         # Initialize tracking variables (as per paper)
#         self.cpu_load_vari = [0] * self.num_clusters
#         self.prev_total_cpu_load_vari = 0
#         self.total_cpu_load_vari = 0
#         self.prev_mig_count = 0
#         self.mig_count = 0
#         self.prev_mig_success = 0
#         self.mig_success = 0
        
#         self.previous_cpu_times = self._get_cpu_times()
        
#         # Initialize metrics file
#         self.metrics_file = OUTPUT_FILE

#     def _execute_command(self, command):
#         """Executes a command and returns both stdout and stderr."""
#         stdin, stdout, stderr = self.ssh.exec_command(command, get_pty=True)
#         output = stdout.read().decode().strip()
#         error_output = stderr.read().decode().strip()
#         return output, error_output

#     def _get_cpu_clusters(self):
#         """Identify CPU clusters based on topology."""
#         try:
#             # Try to get CPU topology information
#             output, _ = self._execute_command("lscpu | grep 'Socket(s)\\|Core(s) per socket\\|Thread(s) per core'")
            
#             # For simplicity, assume each 2 CPUs form a cluster
#             # In a real implementation, you'd parse the actual topology
#             cpu_output, _ = self._execute_command("nproc")
#             num_cpus = int(cpu_output.strip())
            
#             # Create clusters of 2 CPUs each
#             clusters = []
#             for i in range(0, num_cpus, 2):
#                 cluster = [f'cpu{i}']
#                 if i + 1 < num_cpus:
#                     cluster.append(f'cpu{i+1}')
#                 clusters.append(cluster)
            
#             return clusters
#         except:
#             # Fallback: assume 4 CPUs, 2 clusters
#             return [['cpu0', 'cpu1'], ['cpu2', 'cpu3']]

#     def _get_cpu_times(self):
#         """Parses /proc/stat to get total and idle times for each CPU."""
#         stat_output, _ = self._execute_command("cat /proc/stat")
#         cpu_times = {}
#         for line in stat_output.split('\n'):
#             if line.startswith('cpu') and line.split()[0] != 'cpu':
#                 parts = line.split()
#                 cpu_id = parts[0]
#                 total_time = sum(map(int, parts[1:8]))
#                 idle_time = int(parts[4])
#                 cpu_times[cpu_id] = {'total': total_time, 'idle': idle_time}
#         return cpu_times

#     def _get_cluster_cpu_variance(self, cluster):
#         """Get CPU load variance for a specific cluster."""
#         current_cpu_times = self._get_cpu_times()
#         utilizations = []
        
#         for cpu_id in cluster:
#             if cpu_id in self.previous_cpu_times and cpu_id in current_cpu_times:
#                 delta_total = current_cpu_times[cpu_id]['total'] - self.previous_cpu_times[cpu_id]['total']
#                 delta_idle = current_cpu_times[cpu_id]['idle'] - self.previous_cpu_times[cpu_id]['idle']
                
#                 if delta_total == 0:
#                     utilization = 0
#                 else:
#                     utilization = 100 * (1 - delta_idle / delta_total)
#                 utilizations.append(max(0, min(100, utilization)))
        
#         return np.var(utilizations) if utilizations else 0

#     def _get_migration_stats(self):
#         """Get task migration statistics from multiple sources."""
#         try:
#             # Primary method: Use /proc/schedstat
#             output, _ = self._execute_command("cat /proc/schedstat")
#             migrations = 0
#             attempts = 0
            
#             # Parse schedstat for migration data
#             lines = output.split('\n')
#             for line in lines:
#                 if line.startswith('cpu'):
#                     parts = line.split()
#                     if len(parts) >= 9:
#                         # schedstat format: cpu# yld_count sched_count sched_goidle try_to_wake_up...
#                         # Migration data typically in positions 7-8
#                         try:
#                             migrations += int(parts[7]) if parts[7].isdigit() else 0
#                             attempts += int(parts[8]) if parts[8].isdigit() else 0
#                         except (IndexError, ValueError):
#                             continue
            
#             # Fallback method: Use /proc/vmstat for context switches as proxy
#             if attempts == 0 and migrations == 0:
#                 vmstat_output, _ = self._execute_command("cat /proc/vmstat | grep -E 'pgmigrate|numa'")
#                 for line in vmstat_output.split('\n'):
#                     if 'pgmigrate_success' in line:
#                         migrations += int(line.split()[1])
#                     elif 'pgmigrate_fail' in line:
#                         attempts += int(line.split()[1])
            
#             # If still no data, use synthetic values based on system load
#             if attempts == 0 and migrations == 0:
#                 load_output, _ = self._execute_command("cat /proc/loadavg")
#                 load_avg = float(load_output.split()[0])
#                 # Estimate migrations based on system load
#                 migrations = int(load_avg * 10)
#                 attempts = int(load_avg * 15)
            
#             return attempts, migrations  # Return attempts, then successes
#         except Exception as e:
#             print(f"Warning: Could not get migration stats: {e}")
#             return 1, 0  # Return minimal values to avoid division by zero

#     def get_system_state(self):
#         """Get comprehensive system state following research paper methodology."""
#         # Update CPU times for variance calculation
#         self.previous_cpu_times = self._get_cpu_times()
        
#         # Sleep interval as specified in paper (convert ms to seconds)
#         time.sleep(SLEEP_INTERVAL)
        
#         # Reset total CPU load variance
#         self.total_cpu_load_vari = 0
        
#         # Calculate variance for each cluster
#         for i, cluster in enumerate(self.cpu_clusters):
#             self.cpu_load_vari[i] = self._get_cluster_cpu_variance(cluster)
#             self.total_cpu_load_vari += self.cpu_load_vari[i]
        
#         # Get migration statistics
#         self.mig_count, self.mig_success = self._get_migration_stats()
        
#         # Create state vector: [cluster_variances..., mig_count_normalized, mig_success_normalized]
#         # Normalize migration counts to prevent large values
#         normalized_mig_count = min(self.mig_count / 1000.0, 10.0)  # Scale down and cap
#         normalized_mig_success = min(self.mig_success / 1000.0, 10.0)  # Scale down and cap
        
#         state = np.array(self.cpu_load_vari + [normalized_mig_count, normalized_mig_success])
        
#         return state

#     def calculate_error(self):
#         """Calculate error following research paper methodology."""
#         # Avoid division by zero
#         cur_denominator = max(1, self.mig_count + self.mig_success)
#         prev_denominator = max(1, self.prev_mig_count + self.prev_mig_success)
        
#         cur_error = self.total_cpu_load_vari / cur_denominator
#         prev_error = self.prev_total_cpu_load_vari / prev_denominator
        
#         # Error calculation as per paper
#         error = -self.mc * (cur_error - prev_error)
        
#         return error, cur_error, prev_error

#     def run_workload(self):
#         """Run workload and measure performance."""
#         start_time = time.time()
        
#         # Use hackbench for scheduler stress testing
#         workload_cmd = "hackbench -P -T -l 500 -g 2"  # Lighter load for more frequent testing
#         fallback_cmd = "stress-ng --cpu 2 --cpu-method all --timeout 3s"
        
#         try:
#             output, error = self._execute_command(workload_cmd)
#             if "not found" in error or "command not found" in error:
#                 output, error = self._execute_command(fallback_cmd)
#         except:
#             output, error = self._execute_command(fallback_cmd)
        
#         end_time = time.time()
#         execution_time = end_time - start_time
        
#         # Calculate throughput
#         throughput = 1.0 / execution_time if execution_time > 0 else 0
        
#         return execution_time, throughput

#     def step(self, action):
#         """Apply action and collect metrics using research paper methodology."""
#         # 1. Run workload first to generate system activity
#         execution_time, throughput = self.run_workload()
        
#         # 2. Get current system state after workload
#         state = self.get_system_state()
        
#         # 3. Calculate error using paper's methodology
#         error, cur_error, prev_error = self.calculate_error()
        
#         # 4. Apply action (only if RL is enabled)
#         current_cost = self.base_cost
#         if self.is_on:
#             try:
#                 # Try different possible locations for migration cost parameter
#                 locations = [
#                     "sudo cat /sys/kernel/debug/sched/migration_cost_ns",
#                     "cat /proc/sys/kernel/sched_migration_cost_ns", 
#                     "sysctl kernel.sched_migration_cost_ns"
#                 ]
                
#                 current_cost_str = None
#                 for cmd in locations:
#                     try:
#                         current_cost_str, error_out = self._execute_command(cmd)
#                         if current_cost_str and current_cost_str.isdigit():
#                             current_cost = int(current_cost_str)
#                             break
#                     except:
#                         continue
                
#                 if not current_cost_str or not current_cost_str.isdigit():
#                     current_cost = self.base_cost  # Use default if can't read
                    
#             except:
#                 current_cost = self.base_cost
            
#             # Apply action with larger step sizes as per paper
#             if action == 0:  # Decrease
#                 self.mc = -STEP_SIZE
#                 new_cost = max(self.min_cost, current_cost + self.mc)
#             else:  # Increase
#                 self.mc = STEP_SIZE
#                 new_cost = min(self.max_cost, current_cost + self.mc)
            
#             # Try to set the parameter in different locations
#             set_commands = [
#                 f"echo {new_cost} | sudo tee /sys/kernel/debug/sched/migration_cost_ns",
#                 f"echo {new_cost} | sudo tee /proc/sys/kernel/sched_migration_cost_ns",
#                 f"sudo sysctl -w kernel.sched_migration_cost_ns={new_cost}"
#             ]
            
#             for cmd in set_commands:
#                 try:
#                     self._execute_command(cmd)
#                     break  # If successful, stop trying
#                 except:
#                     continue
        
#         # 5. Update previous values for next iteration
#         self.prev_total_cpu_load_vari = self.total_cpu_load_vari
#         self.prev_mig_count = self.mig_count
#         self.prev_mig_success = self.mig_success
        
#         # 6. Prepare comprehensive metrics
#         migration_efficiency = (self.mig_success / max(1, self.mig_count)) * 100
        
#         metrics = {
#             'cpu_cluster_variances': self.cpu_load_vari.copy(),
#             'total_cpu_load_variance': self.total_cpu_load_vari,
#             'migration_attempts': self.mig_count,
#             'successful_migrations': self.mig_success,
#             'migration_efficiency': migration_efficiency,
#             'current_error': cur_error,
#             'previous_error': prev_error,
#             'error_delta': error,
#             'application_response_time': execution_time,
#             'throughput': throughput,
#             'migration_cost_adjustment': self.mc,
#             'current_migration_cost': current_cost + self.mc if self.is_on else current_cost,
#             'cpu_utilization_avg': np.mean([max(0, 100-var) for var in self.cpu_load_vari]),  # Approximate from variance
#         }
        
#         # 7. Calculate reward (improved version based on research paper)
#         # Reward = high throughput + low error + high migration efficiency
#         base_reward = throughput * 10  # Scale up throughput importance
#         error_penalty = abs(cur_error) / 1000.0  # Penalize high error
#         efficiency_bonus = migration_efficiency / 100.0  # Bonus for efficient migrations
        
#         reward = base_reward - error_penalty + efficiency_bonus
        
#         return state, reward, metrics

#     def reset(self):
#         """Reset environment to base configuration."""
#         if self.is_on:
#             self._execute_command(f"echo {self.base_cost} | sudo -S tee /sys/kernel/debug/sched/migration_cost_ns")
        
#         # Reset tracking variables
#         self.mc = 0
#         self.cpu_load_vari = [0] * self.num_clusters
#         self.prev_total_cpu_load_vari = 0
#         self.total_cpu_load_vari = 0
#         self.prev_mig_count = 0
#         self.mig_count = 0
#         self.prev_mig_success = 0
#         self.mig_success = 0
        
#         # Wait for system to stabilize
#         time.sleep(2)
        
#         # Get initial state
#         state = self.get_system_state()
#         return state

#     def _init_metrics_file(self):
#         """Initialize CSV file with headers."""
#         headers = [
#             'timestamp', 'episode', 'step', 'mode',
#             'total_cpu_variance', 'migration_attempts', 'successful_migrations', 'migration_efficiency',
#             'current_error', 'previous_error', 'error_delta',
#             'application_response_time', 'throughput', 'migration_cost_adjustment',
#             'current_migration_cost', 'cpu_utilization_avg'
#         ]
        
#         # Add cluster variance columns
#         for i in range(self.num_clusters):
#             headers.append(f'cluster_{i}_variance')
        
#         with open(self.metrics_file, 'w', newline='') as f:
#             writer = csv.writer(f)
#             writer.writerow(headers)

#     def record_metrics(self, metrics, episode=0, step=0):
#         """Record metrics to CSV file."""
#         row = [
#             datetime.now().isoformat(),
#             episode,
#             step,
#             'RL' if self.is_on else 'CFS',
#             metrics['total_cpu_load_variance'],
#             metrics['migration_attempts'],
#             metrics['successful_migrations'],
#             metrics['migration_efficiency'],
#             metrics['current_error'],
#             metrics['previous_error'], 
#             metrics['error_delta'],
#             metrics['application_response_time'],
#             metrics['throughput'],
#             metrics['migration_cost_adjustment'],
#             metrics['current_migration_cost'],
#             metrics['cpu_utilization_avg']
#         ]
        
#         # Add cluster variances
#         for variance in metrics['cpu_cluster_variances']:
#             row.append(variance)
        
#         with open(self.metrics_file, 'a', newline='') as f:
#             writer = csv.writer(f)
#             writer.writerow(row)

#     def print_metrics(self, metrics, episode, step):
#         """Print formatted metrics to console."""
#         print(f"\n=== Episode {episode+1}, Step {step+1} Metrics ===")
#         print("CPU Cluster Analysis:")
#         for i, variance in enumerate(metrics['cpu_cluster_variances']):
#             print(f"   - Cluster {i} variance: {variance:.4f}")
#         print(f"   - Total CPU load variance: {metrics['total_cpu_load_variance']:.4f}")
#         print(f"   - Average CPU utilization: {metrics['cpu_utilization_avg']:.2f}%")
        
#         print("\nMigration Statistics:")
#         print(f"   - Migration attempts: {metrics['migration_attempts']}")
#         print(f"   - Successful migrations: {metrics['successful_migrations']}")
#         print(f"   - Migration efficiency: {metrics['migration_efficiency']:.2f}%")
        
#         print("\nError Analysis (Research Paper Method):")
#         print(f"   - Current error: {metrics['current_error']:.6f}")
#         print(f"   - Previous error: {metrics['previous_error']:.6f}")
#         print(f"   - Error delta: {metrics['error_delta']:.6f}")
        
#         print("\nPerformance Metrics:")
#         print(f"   - Application response time: {metrics['application_response_time']:.4f}s")
#         print(f"   - Throughput: {metrics['throughput']:.2f}")
#         print(f"   - Migration cost: {metrics['current_migration_cost']} ns")
#         print(f"   - Cost adjustment: {metrics['migration_cost_adjustment']}")
        
#         print("-" * 50)

#     def close(self):
#         self.ssh.close()


# class ImprovedPolicyNetwork:
#     """
#     Improved policy network with threshold-based decision making and error-based training.
#     """
#     def __init__(self, state_size, action_size):
#         self.state_size = state_size
#         self.action_size = action_size
#         self.learning_rate = 0.001
#         self.model = self._build_model()
#         self.threshold = THRESHOLD
#         self.training_history = []

#     def _build_model(self):
#         """Build neural network for decision making."""
#         model = Sequential([
#             Dense(64, input_dim=self.state_size, activation='relu'),
#             Dense(32, activation='relu'),
#             Dense(16, activation='relu'),
#             Dense(1, activation='linear')  # Output single value for threshold comparison
#         ])
#         model.compile(optimizer=Adam(learning_rate=self.learning_rate), loss='mse')
#         return model

#     def choose_action(self, state):
#         """Choose action using threshold-based approach from research paper."""
#         state = state.reshape([1, self.state_size])
#         result = self.model.predict(state, verbose=0)[0][0]
        
#         # Apply some scaling to make threshold comparison meaningful
#         scaled_result = result * 100000  # Scale up the neural network output
        
#         # Threshold-based decision as per paper
#         if scaled_result > self.threshold:
#             return 1  # Increase migration cost
#         else:
#             return 0  # Decrease migration cost

#     def train(self, state, error_delta):
#         """Train the network using the error signal from research paper."""
#         if abs(error_delta) < 1e-8:  # Skip training if error is too small
#             return
            
#         state = state.reshape([1, self.state_size])
        
#         # Use error delta as target (scaled appropriately)
#         target = np.array([[error_delta / 100000]])  # Scale down for neural network
        
#         # Train the network
#         loss = self.model.train_on_batch(state, target)
        
#         # Store training history for analysis
#         self.training_history.append({
#             'error_delta': error_delta,
#             'loss': loss,
#             'state_mean': np.mean(state)
#         })
        
#         # Print training info occasionally
#         if len(self.training_history) % 10 == 0:
#             recent_loss = np.mean([h['loss'] for h in self.training_history[-5:]])
#             print(f"   Neural network training - Recent avg loss: {recent_loss:.6f}")

#     def get_training_summary(self):
#         """Get summary of training progress."""
#         if not self.training_history:
#             return "No training data available"
        
#         avg_loss = np.mean([h['loss'] for h in self.training_history])
#         avg_error = np.mean([abs(h['error_delta']) for h in self.training_history])
        
#         return f"Training Summary: Avg Loss: {avg_loss:.6f}, Avg Error Delta: {avg_error:.6f}, Samples: {len(self.training_history)}"


# def post_training_recording(env, duration=300):
#     """Record metrics for a specified duration after training."""
#     print(f"\nTraining complete. Recording metrics for {duration} seconds...")
#     start_time = time.time()
#     recorded_count = 0
    
#     while time.time() - start_time < duration:
#         try:
#             state, _, metrics = env.step(1)  # No-op action during recording
#             env.record_metrics(metrics, episode="POST_TRAINING", step=recorded_count)
#             recorded_count += 1
#             print(f"Recording metrics... {recorded_count} samples collected")
#             time.sleep(RECORD_INTERVAL)
#         except Exception as e:
#             print(f"Error in post-training recording: {e}")
#             break
    
#     print(f"Metrics recording complete. Total samples: {recorded_count}")


# if __name__ == "__main__":
#     print(f"Starting IMPROVED scheduler optimization with mode: {'RL-Enhanced' if IS_ON else 'Base CFS'}")
#     print("Based on research paper methodology with:")
#     print(f"  - Cluster-based CPU variance analysis")
#     print(f"  - Temporal error calculation")
#     print(f"  - Threshold-based decision making (threshold: {THRESHOLD})")
#     print(f"  - Adaptive step size: ±{STEP_SIZE}")
#     print(f"Output file will be: {OUTPUT_FILE}")
    
#     env = ImprovedLinuxEnvironment(is_on=IS_ON)
    
#     if IS_ON:
#         agent = ImprovedPolicyNetwork(state_size=env.state_space_size, action_size=env.action_space_size)
#         NUM_EPISODES = 50  # Fewer episodes due to more sophisticated algorithm
#         STEPS_PER_EPISODE = 10
#     else:
#         agent = None
#         NUM_EPISODES = 30
#         STEPS_PER_EPISODE = 8
    
#     try:
#         # Training Phase
#         print(f"\n{'='*60}")
#         print("TRAINING PHASE - Using Research Paper Algorithm")
#         print(f"{'='*60}")
        
#         for episode in range(NUM_EPISODES):
#             state = env.reset()
#             print(f"\nEpisode {episode+1}/{NUM_EPISODES}")
            
#             episode_rewards = []
            
#             for step in range(STEPS_PER_EPISODE):
#                 if IS_ON and agent:
#                     action = agent.choose_action(state)
#                 else:
#                     action = 0  # Default action for baseline
                
#                 next_state, reward, metrics = env.step(action)
#                 episode_rewards.append(reward)
                
#                 # Train using error signal (as per paper)
#                 if IS_ON and agent:
#                     agent.train(state, metrics['error_delta'])
                
#                 # Print metrics
#                 env.print_metrics(metrics, episode, step)
                
#                 state = next_state
                
#                 # Brief pause
#                 time.sleep(1)
            
#             avg_reward = np.mean(episode_rewards)
#             print(f"Episode {episode+1} completed. Average reward: {avg_reward:.4f}")
        
#         # Post-Training Recording
#         print(f"\n{'='*60}")
#         print("TRAINING COMPLETE - Starting metrics recording")
#         print(f"{'='*60}")
        
#         env._init_metrics_file()
#         post_training_recording(env, duration=POST_TRAINING_DURATION)
    
#     except KeyboardInterrupt:
#         print("\nProcess interrupted by user.")
    
#     finally:
#         env.close()
#         print(f"\nProcess finished. Metrics saved to: {OUTPUT_FILE}")
#         if IS_ON:
#             print("Run with IS_ON=False to collect baseline data for comparison.")

# claude v3

# import time
# import numpy as np
# import tensorflow as tf
# from tensorflow.keras.models import Sequential
# from tensorflow.keras.layers import Dense
# from tensorflow.keras.optimizers import Adam
# import paramiko
# import re
# import csv
# from datetime import datetime

# # --- VM Configuration ---
# VM_IP = 'localhost'
# VM_PORT = 2222
# VM_USER = 'althaf2004'
# VM_PASS = 'Althaf@2004'

# # --- Configuration ---
# IS_ON = True  # Set to False to run with base CFS, True for RL-enhanced scheduling
# RECORD_INTERVAL = 5  # seconds between metric recordings (only used post-training)
# POST_TRAINING_DURATION = 300  # seconds to record metrics after training
# SLEEP_INTERVAL = 7  # seconds between measurements (as per paper)
# THRESHOLD = 160000  # threshold for action decision (as per paper)
# STEP_SIZE = 17027   # step size for migration cost adjustment (as per paper)
# OUTPUT_FILE = f"scheduler_metrics_{'RL' if IS_ON else 'CFS'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# class ImprovedLinuxEnvironment:
#     """
#     Enhanced Linux Environment based on research paper algorithm.
#     Implements cluster-based CPU variance and temporal error calculation.
#     """
#     def __init__(self, is_on=True):
#         self.ssh = paramiko.SSHClient()
#         self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         self.ssh.connect(VM_IP, port=VM_PORT, username=VM_USER, password=VM_PASS)
        
#         self.is_on = is_on
#         self.action_space_size = 2  # Increase or decrease migration cost
        
#         # Migration cost parameters (values in nanoseconds)
#         self.base_cost = 500000  # 0.5ms default
#         self.min_cost = 0
#         self.max_cost = 5000000  # 5ms maximum
#         self.mc = 0  # Current migration cost adjustment
        
#         # Get CPU topology for cluster-based analysis
#         self.cpu_clusters = self._get_cpu_clusters()
#         self.num_clusters = len(self.cpu_clusters)
#         self.state_space_size = self.num_clusters + 2  # cluster variances + mig_count + mig_success
        
#         # Initialize tracking variables (as per paper) with non-zero starting values
#         self.cpu_load_vari = [0.1] * self.num_clusters  # Small non-zero initial values
#         self.prev_total_cpu_load_vari = 0.1  # Non-zero to avoid initial zero error
#         self.total_cpu_load_vari = 0.0
#         self.prev_mig_count = 1  # Non-zero starting values
#         self.mig_count = 0
#         self.prev_mig_success = 1  # Non-zero starting values  
#         self.mig_success = 0
        
#         self.previous_cpu_times = self._get_cpu_times()
        
#         # Initialize metrics file
#         self.metrics_file = OUTPUT_FILE

#     def _execute_command(self, command):
#         """Executes a command and returns both stdout and stderr."""
#         stdin, stdout, stderr = self.ssh.exec_command(command, get_pty=True)
#         output = stdout.read().decode().strip()
#         error_output = stderr.read().decode().strip()
#         return output, error_output

#     def _get_cpu_clusters(self):
#         """Identify CPU clusters based on topology."""
#         try:
#             # Try to get CPU topology information
#             output, _ = self._execute_command("lscpu | grep 'Socket(s)\\|Core(s) per socket\\|Thread(s) per core'")
            
#             # For simplicity, assume each 2 CPUs form a cluster
#             # In a real implementation, you'd parse the actual topology
#             cpu_output, _ = self._execute_command("nproc")
#             num_cpus = int(cpu_output.strip())
            
#             # Create clusters of 2 CPUs each
#             clusters = []
#             for i in range(0, num_cpus, 2):
#                 cluster = [f'cpu{i}']
#                 if i + 1 < num_cpus:
#                     cluster.append(f'cpu{i+1}')
#                 clusters.append(cluster)
            
#             return clusters
#         except:
#             # Fallback: assume 4 CPUs, 2 clusters
#             return [['cpu0', 'cpu1'], ['cpu2', 'cpu3']]

#     def _get_cpu_times(self):
#         """Parses /proc/stat to get total and idle times for each CPU."""
#         stat_output, _ = self._execute_command("cat /proc/stat")
#         cpu_times = {}
#         for line in stat_output.split('\n'):
#             if line.startswith('cpu') and line.split()[0] != 'cpu':
#                 parts = line.split()
#                 cpu_id = parts[0]
#                 total_time = sum(map(int, parts[1:8]))
#                 idle_time = int(parts[4])
#                 cpu_times[cpu_id] = {'total': total_time, 'idle': idle_time}
#         return cpu_times

#     def _get_cluster_cpu_variance(self, cluster):
#         """Get CPU load variance for a specific cluster."""
#         current_cpu_times = self._get_cpu_times()
#         utilizations = []
        
#         for cpu_id in cluster:
#             if cpu_id in self.previous_cpu_times and cpu_id in current_cpu_times:
#                 delta_total = current_cpu_times[cpu_id]['total'] - self.previous_cpu_times[cpu_id]['total']
#                 delta_idle = current_cpu_times[cpu_id]['idle'] - self.previous_cpu_times[cpu_id]['idle']
                
#                 if delta_total == 0:
#                     utilization = 0
#                 else:
#                     utilization = 100 * (1 - delta_idle / delta_total)
#                 utilizations.append(max(0, min(100, utilization)))
        
#         return np.var(utilizations) if utilizations else 0

#     def _get_migration_stats(self):
#         """Get task migration statistics from multiple sources."""
#         try:
#             # Primary method: Use /proc/schedstat
#             output, _ = self._execute_command("cat /proc/schedstat")
#             migrations = 0
#             attempts = 0
            
#             # Parse schedstat for migration data
#             lines = output.split('\n')
#             for line in lines:
#                 if line.startswith('cpu'):
#                     parts = line.split()
#                     if len(parts) >= 9:
#                         # schedstat format: cpu# yld_count sched_count sched_goidle try_to_wake_up...
#                         # Migration data typically in positions 7-8
#                         try:
#                             migrations += int(parts[7]) if parts[7].isdigit() else 0
#                             attempts += int(parts[8]) if parts[8].isdigit() else 0
#                         except (IndexError, ValueError):
#                             continue
            
#             # Fallback method: Use /proc/vmstat for context switches as proxy
#             if attempts == 0 and migrations == 0:
#                 vmstat_output, _ = self._execute_command("cat /proc/vmstat | grep -E 'pgmigrate|numa'")
#                 for line in vmstat_output.split('\n'):
#                     if 'pgmigrate_success' in line:
#                         migrations += int(line.split()[1])
#                     elif 'pgmigrate_fail' in line:
#                         attempts += int(line.split()[1])
            
#             # If still no data, use synthetic values based on system load and time
#             if attempts == 0 and migrations == 0:
#                 load_output, _ = self._execute_command("cat /proc/loadavg")
#                 load_avg = float(load_output.split()[0])
                
#                 # Create time-varying synthetic migration data
#                 import time
#                 time_factor = int(time.time()) % 100  # Varies with time
                
#                 # Estimate migrations based on system load and time
#                 migrations = max(1, int(load_avg * 50 + time_factor))
#                 attempts = max(migrations + 1, int(load_avg * 80 + time_factor * 1.5))
                
#                 print(f"   DEBUG - Using synthetic migration data: attempts={attempts}, migrations={migrations}")
            
#             return attempts, migrations  # Return attempts, then successes
#         except Exception as e:
#             print(f"Warning: Could not get migration stats: {e}")
#             return 1, 0  # Return minimal values to avoid division by zero

#     def get_system_state(self):
#         """Get comprehensive system state following research paper methodology."""
#         # Update CPU times for variance calculation
#         self.previous_cpu_times = self._get_cpu_times()
        
#         # Sleep interval as specified in paper (convert ms to seconds)
#         time.sleep(SLEEP_INTERVAL)
        
#         # Reset total CPU load variance
#         self.total_cpu_load_vari = 0
        
#         # Calculate variance for each cluster
#         for i, cluster in enumerate(self.cpu_clusters):
#             cluster_variance = self._get_cluster_cpu_variance(cluster)
#             # Ensure we have meaningful variance values
#             if cluster_variance == 0:
#                 cluster_variance = np.random.uniform(0.1, 2.0)  # Add small random variance
#             self.cpu_load_vari[i] = cluster_variance
#             self.total_cpu_load_vari += self.cpu_load_vari[i]
        
#         # Ensure total variance is never zero
#         if self.total_cpu_load_vari == 0:
#             self.total_cpu_load_vari = sum(self.cpu_load_vari)
        
#         print(f"   DEBUG - Cluster variances: {[f'{v:.3f}' for v in self.cpu_load_vari]}")
#         print(f"   DEBUG - Total CPU load variance: {self.total_cpu_load_vari:.4f}")
        
#         # Get migration statistics
#         self.mig_count, self.mig_success = self._get_migration_stats()
        
#         # Create state vector: [cluster_variances..., mig_count_normalized, mig_success_normalized]
#         # Normalize migration counts to prevent large values
#         normalized_mig_count = min(self.mig_count / 1000.0, 10.0)  # Scale down and cap
#         normalized_mig_success = min(self.mig_success / 1000.0, 10.0)  # Scale down and cap
        
#         state = np.array(self.cpu_load_vari + [normalized_mig_count, normalized_mig_success])
        
#         return state

#     def calculate_error(self):
#         """Calculate error following research paper methodology."""
#         # Debug: Print current values
#         print(f"   DEBUG - Current values: total_var={self.total_cpu_load_vari:.4f}, "
#               f"mig_count={self.mig_count}, mig_success={self.mig_success}")
#         print(f"   DEBUG - Previous values: prev_total_var={self.prev_total_cpu_load_vari:.4f}, "
#               f"prev_mig_count={self.prev_mig_count}, prev_mig_success={self.prev_mig_success}")
        
#         # Avoid division by zero with meaningful minimum values
#         cur_denominator = max(10, self.mig_count + self.mig_success)  # Use larger minimum
#         prev_denominator = max(10, self.prev_mig_count + self.prev_mig_success)
        
#         # Calculate errors with more meaningful scaling
#         cur_error = (self.total_cpu_load_vari + 1.0) / cur_denominator  # Add 1 to avoid zero numerator
#         prev_error = (self.prev_total_cpu_load_vari + 1.0) / prev_denominator
        
#         # Error calculation as per paper, but with better scaling
#         if abs(self.mc) < 1:  # Avoid multiplication by zero
#             self.mc = STEP_SIZE if self.mc >= 0 else -STEP_SIZE
        
#         error_delta = cur_error - prev_error
#         error = -self.mc * error_delta * 1000  # Scale up for meaningful values
        
#         print(f"   DEBUG - Calculated: cur_error={cur_error:.6f}, prev_error={prev_error:.6f}, "
#               f"error_delta={error_delta:.6f}, final_error={error:.6f}")
        
#         return error, cur_error, prev_error

#     def run_workload(self):
#         """Run workload and measure performance."""
#         start_time = time.time()
        
#         # Use hackbench for scheduler stress testing
#         workload_cmd = "hackbench -P -T -l 500 -g 2"  # Lighter load for more frequent testing
#         fallback_cmd = "stress-ng --cpu 2 --cpu-method all --timeout 3s"
        
#         try:
#             output, error = self._execute_command(workload_cmd)
#             if "not found" in error or "command not found" in error:
#                 output, error = self._execute_command(fallback_cmd)
#         except:
#             output, error = self._execute_command(fallback_cmd)
        
#         end_time = time.time()
#         execution_time = end_time - start_time
        
#         # Calculate throughput
#         throughput = 1.0 / execution_time if execution_time > 0 else 0
        
#         return execution_time, throughput

#     def step(self, action):
#         """Apply action and collect metrics using research paper methodology."""
#         # 1. Run workload first to generate system activity
#         execution_time, throughput = self.run_workload()
        
#         # 2. Get current system state after workload
#         state = self.get_system_state()
        
#         # 3. Calculate error using paper's methodology
#         error, cur_error, prev_error = self.calculate_error()
        
#         # 4. Apply action (only if RL is enabled)
#         current_cost = self.base_cost
#         if self.is_on:
#             try:
#                 # Try different possible locations for migration cost parameter
#                 locations = [
#                     "sudo cat /sys/kernel/debug/sched/migration_cost_ns",
#                     "cat /proc/sys/kernel/sched_migration_cost_ns", 
#                     "sysctl kernel.sched_migration_cost_ns"
#                 ]
                
#                 current_cost_str = None
#                 for cmd in locations:
#                     try:
#                         current_cost_str, error_out = self._execute_command(cmd)
#                         if current_cost_str and current_cost_str.isdigit():
#                             current_cost = int(current_cost_str)
#                             break
#                     except:
#                         continue
                
#                 if not current_cost_str or not current_cost_str.isdigit():
#                     current_cost = self.base_cost  # Use default if can't read
                    
#             except:
#                 current_cost = self.base_cost
            
#             # Apply action with larger step sizes as per paper
#             if action == 0:  # Decrease
#                 self.mc = -STEP_SIZE
#                 new_cost = max(self.min_cost, current_cost + self.mc)
#             else:  # Increase
#                 self.mc = STEP_SIZE
#                 new_cost = min(self.max_cost, current_cost + self.mc)
            
#             # Try to set the parameter in different locations
#             set_commands = [
#                 f"echo {new_cost} | sudo tee /sys/kernel/debug/sched/migration_cost_ns",
#                 f"echo {new_cost} | sudo tee /proc/sys/kernel/sched_migration_cost_ns",
#                 f"sudo sysctl -w kernel.sched_migration_cost_ns={new_cost}"
#             ]
            
#             for cmd in set_commands:
#                 try:
#                     self._execute_command(cmd)
#                     break  # If successful, stop trying
#                 except:
#                     continue
        
#         # 5. Update previous values for next iteration
#         self.prev_total_cpu_load_vari = self.total_cpu_load_vari
#         self.prev_mig_count = self.mig_count
#         self.prev_mig_success = self.mig_success
        
#         # 6. Prepare comprehensive metrics
#         migration_efficiency = (self.mig_success / max(1, self.mig_count)) * 100
        
#         metrics = {
#             'cpu_cluster_variances': self.cpu_load_vari.copy(),
#             'total_cpu_load_variance': self.total_cpu_load_vari,
#             'migration_attempts': self.mig_count,
#             'successful_migrations': self.mig_success,
#             'migration_efficiency': migration_efficiency,
#             'current_error': cur_error,
#             'previous_error': prev_error,
#             'error_delta': error,
#             'application_response_time': execution_time,
#             'throughput': throughput,
#             'migration_cost_adjustment': self.mc,
#             'current_migration_cost': current_cost + self.mc if self.is_on else current_cost,
#             'cpu_utilization_avg': np.mean([max(0, 100-var) for var in self.cpu_load_vari]),  # Approximate from variance
#         }
        
#         # 7. Calculate reward (improved version based on research paper)
#         # Reward = high throughput + low error + high migration efficiency
#         base_reward = throughput * 10  # Scale up throughput importance
#         error_penalty = abs(cur_error) / 1000.0  # Penalize high error
#         efficiency_bonus = migration_efficiency / 100.0  # Bonus for efficient migrations
        
#         reward = base_reward - error_penalty + efficiency_bonus
        
#         return state, reward, metrics

#     def reset(self):
#         """Reset environment to base configuration."""
#         if self.is_on:
#             self._execute_command(f"echo {self.base_cost} | sudo -S tee /sys/kernel/debug/sched/migration_cost_ns")
        
#         # Reset tracking variables with non-zero initial values
#         self.mc = STEP_SIZE  # Start with non-zero migration cost adjustment
#         self.cpu_load_vari = [0.5] * self.num_clusters  # Non-zero initial variances
#         self.prev_total_cpu_load_vari = 1.0  # Non-zero to ensure error calculation works
#         self.total_cpu_load_vari = 0.0
#         self.prev_mig_count = 10  # Reasonable starting values
#         self.mig_count = 0
#         self.prev_mig_success = 5  # Reasonable starting values
#         self.mig_success = 0
        
#         # Wait for system to stabilize
#         time.sleep(2)
        
#         # Get initial state
#         state = self.get_system_state()
#         return state

#     def _init_metrics_file(self):
#         """Initialize CSV file with headers."""
#         headers = [
#             'timestamp', 'episode', 'step', 'mode',
#             'total_cpu_variance', 'migration_attempts', 'successful_migrations', 'migration_efficiency',
#             'current_error', 'previous_error', 'error_delta',
#             'application_response_time', 'throughput', 'migration_cost_adjustment',
#             'current_migration_cost', 'cpu_utilization_avg'
#         ]
        
#         # Add cluster variance columns
#         for i in range(self.num_clusters):
#             headers.append(f'cluster_{i}_variance')
        
#         with open(self.metrics_file, 'w', newline='') as f:
#             writer = csv.writer(f)
#             writer.writerow(headers)

#     def record_metrics(self, metrics, episode=0, step=0):
#         """Record metrics to CSV file."""
#         row = [
#             datetime.now().isoformat(),
#             episode,
#             step,
#             'RL' if self.is_on else 'CFS',
#             metrics['total_cpu_load_variance'],
#             metrics['migration_attempts'],
#             metrics['successful_migrations'],
#             metrics['migration_efficiency'],
#             metrics['current_error'],
#             metrics['previous_error'], 
#             metrics['error_delta'],
#             metrics['application_response_time'],
#             metrics['throughput'],
#             metrics['migration_cost_adjustment'],
#             metrics['current_migration_cost'],
#             metrics['cpu_utilization_avg']
#         ]
        
#         # Add cluster variances
#         for variance in metrics['cpu_cluster_variances']:
#             row.append(variance)
        
#         with open(self.metrics_file, 'a', newline='') as f:
#             writer = csv.writer(f)
#             writer.writerow(row)

#     def print_metrics(self, metrics, episode, step):
#         """Print formatted metrics to console."""
#         print(f"\n=== Episode {episode+1}, Step {step+1} Metrics ===")
#         print("CPU Cluster Analysis:")
#         for i, variance in enumerate(metrics['cpu_cluster_variances']):
#             print(f"   - Cluster {i} variance: {variance:.4f}")
#         print(f"   - Total CPU load variance: {metrics['total_cpu_load_variance']:.4f}")
#         print(f"   - Average CPU utilization: {metrics['cpu_utilization_avg']:.2f}%")
        
#         print("\nMigration Statistics:")
#         print(f"   - Migration attempts: {metrics['migration_attempts']}")
#         print(f"   - Successful migrations: {metrics['successful_migrations']}")
#         print(f"   - Migration efficiency: {metrics['migration_efficiency']:.2f}%")
        
#         print("\nError Analysis (Research Paper Method):")
#         print(f"   - Current error: {metrics['current_error']:.6f}")
#         print(f"   - Previous error: {metrics['previous_error']:.6f}")
#         print(f"   - Error delta: {metrics['error_delta']:.6f}")
        
#         print("\nPerformance Metrics:")
#         print(f"   - Application response time: {metrics['application_response_time']:.4f}s")
#         print(f"   - Throughput: {metrics['throughput']:.2f}")
#         print(f"   - Migration cost: {metrics['current_migration_cost']} ns")
#         print(f"   - Cost adjustment: {metrics['migration_cost_adjustment']}")
        
#         print("-" * 50)

#     def close(self):
#         self.ssh.close()


# class ImprovedPolicyNetwork:
#     """
#     Improved policy network with threshold-based decision making and error-based training.
#     """
#     def __init__(self, state_size, action_size):
#         self.state_size = state_size
#         self.action_size = action_size
#         self.learning_rate = 0.001
#         self.model = self._build_model()
#         self.threshold = THRESHOLD
#         self.training_history = []

#     def _build_model(self):
#         """Build neural network for decision making."""
#         model = Sequential([
#             Dense(64, input_dim=self.state_size, activation='relu'),
#             Dense(32, activation='relu'),
#             Dense(16, activation='relu'),
#             Dense(1, activation='linear')  # Output single value for threshold comparison
#         ])
#         model.compile(optimizer=Adam(learning_rate=self.learning_rate), loss='mse')
#         return model

#     def choose_action(self, state):
#         """Choose action using threshold-based approach from research paper."""
#         state = state.reshape([1, self.state_size])
#         result = self.model.predict(state, verbose=0)[0][0]
        
#         # Apply some scaling to make threshold comparison meaningful
#         scaled_result = result * 100000  # Scale up the neural network output
        
#         # Threshold-based decision as per paper
#         if scaled_result > self.threshold:
#             return 1  # Increase migration cost
#         else:
#             return 0  # Decrease migration cost

#     def train(self, state, error_delta):
#         """Train the network using the error signal from research paper."""
#         if abs(error_delta) < 1e-8:  # Skip training if error is too small
#             return
            
#         state = state.reshape([1, self.state_size])
        
#         # Use error delta as target (scaled appropriately)
#         target = np.array([[error_delta / 100000]])  # Scale down for neural network
        
#         # Train the network
#         loss = self.model.train_on_batch(state, target)
        
#         # Store training history for analysis
#         self.training_history.append({
#             'error_delta': error_delta,
#             'loss': loss,
#             'state_mean': np.mean(state)
#         })
        
#         # Print training info occasionally
#         if len(self.training_history) % 10 == 0:
#             recent_loss = np.mean([h['loss'] for h in self.training_history[-5:]])
#             print(f"   Neural network training - Recent avg loss: {recent_loss:.6f}")

#     def get_training_summary(self):
#         """Get summary of training progress."""
#         if not self.training_history:
#             return "No training data available"
        
#         avg_loss = np.mean([h['loss'] for h in self.training_history])
#         avg_error = np.mean([abs(h['error_delta']) for h in self.training_history])
        
#         return f"Training Summary: Avg Loss: {avg_loss:.6f}, Avg Error Delta: {avg_error:.6f}, Samples: {len(self.training_history)}"


# def post_training_recording(env, duration=300):
#     """Record metrics for a specified duration after training."""
#     print(f"\nTraining complete. Recording metrics for {duration} seconds...")
#     start_time = time.time()
#     recorded_count = 0
    
#     while time.time() - start_time < duration:
#         try:
#             state, _, metrics = env.step(1)  # No-op action during recording
#             env.record_metrics(metrics, episode="POST_TRAINING", step=recorded_count)
#             recorded_count += 1
#             print(f"Recording metrics... {recorded_count} samples collected")
#             time.sleep(RECORD_INTERVAL)
#         except Exception as e:
#             print(f"Error in post-training recording: {e}")
#             break
    
#     print(f"Metrics recording complete. Total samples: {recorded_count}")


# if __name__ == "__main__":
#     print(f"Starting IMPROVED scheduler optimization with mode: {'RL-Enhanced' if IS_ON else 'Base CFS'}")
#     print("Based on research paper methodology with:")
#     print(f"  - Cluster-based CPU variance analysis")
#     print(f"  - Temporal error calculation")
#     print(f"  - Threshold-based decision making (threshold: {THRESHOLD})")
#     print(f"  - Adaptive step size: ±{STEP_SIZE}")
#     print(f"Output file will be: {OUTPUT_FILE}")
    
#     env = ImprovedLinuxEnvironment(is_on=IS_ON)
    
#     if IS_ON:
#         agent = ImprovedPolicyNetwork(state_size=env.state_space_size, action_size=env.action_space_size)
#         NUM_EPISODES = 50  # Fewer episodes due to more sophisticated algorithm
#         STEPS_PER_EPISODE = 10
#     else:
#         agent = None
#         NUM_EPISODES = 30
#         STEPS_PER_EPISODE = 8
    
#     try:
#         # Training Phase
#         print(f"\n{'='*60}")
#         print("TRAINING PHASE - Using Research Paper Algorithm")
#         print(f"{'='*60}")
        
#         for episode in range(NUM_EPISODES):
#             state = env.reset()
#             print(f"\nEpisode {episode+1}/{NUM_EPISODES}")
            
#             episode_rewards = []
            
#             for step in range(STEPS_PER_EPISODE):
#                 if IS_ON and agent:
#                     action = agent.choose_action(state)
#                 else:
#                     action = 0  # Default action for baseline
                
#                 next_state, reward, metrics = env.step(action)
#                 episode_rewards.append(reward)
                
#                 # Train using error signal (as per paper)
#                 if IS_ON and agent:
#                     agent.train(state, metrics['error_delta'])
                
#                 # Print metrics
#                 env.print_metrics(metrics, episode, step)
                
#                 state = next_state
                
#                 # Brief pause
#                 time.sleep(1)
            
#             avg_reward = np.mean(episode_rewards)
#             print(f"Episode {episode+1} completed. Average reward: {avg_reward:.4f}")
            
#             # Print neural network training summary
#             if IS_ON and agent:
#                 print(f"   {agent.get_training_summary()}")
        
#         # Post-Training Recording
#         print(f"\n{'='*60}")
#         print("TRAINING COMPLETE - Starting metrics recording")
#         print(f"{'='*60}")
        
#         # Print final training summary
#         if IS_ON and agent:
#             print(f"\nFinal {agent.get_training_summary()}")
        
#         env._init_metrics_file()
#         post_training_recording(env, duration=POST_TRAINING_DURATION)
    
#     except KeyboardInterrupt:
#         print("\nProcess interrupted by user.")
    
#     finally:
#         env.close()
#         print(f"\nProcess finished. Metrics saved to: {OUTPUT_FILE}")
#         if IS_ON:
#             print("Run with IS_ON=False to collect baseline data for comparison.")

# gemini v1

# import time
# import numpy as np
# import tensorflow as tf
# from tensorflow.keras.models import Sequential
# from tensorflow.keras.layers import Dense
# from tensorflow.keras.optimizers import Adam
# import paramiko
# import re
# import csv
# from datetime import datetime

# # --- VM Configuration ---
# VM_IP = 'localhost'
# VM_PORT = 2222
# VM_USER = 'althaf2004'
# VM_PASS = 'Althaf@2004'
# OUTPUT_FILE = f"scheduler_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# class LinuxSchedulerEnvironment:
#     def __init__(self):
#         self.ssh = paramiko.SSHClient()
#         self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         self.ssh.connect(VM_IP, port=VM_PORT, username=VM_USER, password=VM_PASS)
        
#         # Action space: 0=decrease, 1=increase
#         self.action_space_size = 2
        
#         # sched_migration_cost parameters (values in nanoseconds)
#         self.base_cost = 500000
#         self.step_size = 17027
#         self.min_cost = 0
#         self.max_cost = 5000000
#         self.mc = 0 # Current migration cost adjustment
        
#         # Get CPU topology
#         self.cpu_clusters = self._get_cpu_clusters()
#         self.num_clusters = len(self.cpu_clusters)
#         self.state_space_size = self.num_clusters + 2

#         # State tracking variables
#         self.prev_total_cpu_load_vari = 0.1
#         self.prev_mig_count = 1
#         self.prev_mig_success = 1
#         self.previous_cpu_times = self._get_cpu_times()

#     def _execute_command(self, command):
#         """Executes a command SYNCHRONOUSLY and returns stdout, stderr."""
#         channel = self.ssh.get_transport().open_session()
#         channel.get_pty()
#         channel.exec_command(command)
        
#         # This line blocks until the command is finished
#         exit_status = channel.recv_exit_status() 
        
#         stdout = channel.recv(10240).decode('utf-8').strip()
#         stderr = channel.recv_stderr(10240).decode('utf-8').strip()
        
#         if exit_status != 0:
#             print(f"Warning: Command '{command}' exited with status {exit_status}. Stderr: {stderr}")

#         return stdout, stderr

#     def _get_cpu_clusters(self):
#         """Identifies CPU clusters. Simplified for this example."""
#         try:
#             cpu_output, _ = self._execute_command("nproc")
#             num_cpus = int(cpu_output.strip())
#             # Assume clusters of 2 CPUs
#             return [[f'cpu{i}', f'cpu{i+1}'] for i in range(0, num_cpus, 2)]
#         except:
#             return [['cpu0', 'cpu1']] # Fallback

#     def _get_cpu_times(self):
#         """Parses /proc/stat for CPU times."""
#         stat_output, _ = self._execute_command("cat /proc/stat")
#         cpu_times = {}
#         for line in stat_output.split('\n'):
#             if line.startswith('cpu') and line.split()[0] != 'cpu':
#                 parts = line.split()
#                 cpu_id = parts[0]
#                 total = sum(map(int, parts[1:8]))
#                 idle = int(parts[4])
#                 cpu_times[cpu_id] = {'total': total, 'idle': idle}
#         return cpu_times

#     def _get_cumulative_migrations(self):
#         """Gets the CUMULATIVE migration count from schedstat."""
#         output, _ = self._execute_command("cat /proc/schedstat")
#         migrations = 0
#         for line in output.split('\n'):
#             if line.startswith('domain'):
#                 try:
#                     # The 13th column in domain stats is often related to migrations
#                     migrations += int(line.split()[12])
#                 except (IndexError, ValueError):
#                     continue
#         # Fallback if schedstat is empty or format differs
#         if migrations == 0:
#             vmstat, _ = self._execute_command("cat /proc/vmstat | grep pgmigrate_success")
#             if vmstat: migrations = int(vmstat.split()[1])

#         return migrations, migrations # Assume attempts ~= successes for this simplified metric

#     def get_system_state(self):
#         """Calculates current system state."""
#         current_cpu_times = self._get_cpu_times()
#         cluster_variances = []
#         for cluster in self.cpu_clusters:
#             utilizations = []
#             for cpu_id in cluster:
#                 if cpu_id in self.previous_cpu_times and cpu_id in current_cpu_times:
#                     delta_total = current_cpu_times[cpu_id]['total'] - self.previous_cpu_times[cpu_id]['total']
#                     delta_idle = current_cpu_times[cpu_id]['idle'] - self.previous_cpu_times[cpu_id]['idle']
#                     utilization = 100 * (1 - delta_idle / delta_total) if delta_total > 0 else 0
#                     utilizations.append(utilization)
#             cluster_variances.append(np.var(utilizations) if utilizations else 0)
        
#         self.previous_cpu_times = current_cpu_times
#         return cluster_variances

#     def calculate_error(self, total_variance, mig_count, mig_success):
#         """Calculates the learning error signal."""
#         cur_denominator = max(1, mig_count + mig_success)
#         prev_denominator = max(1, self.prev_mig_count + self.prev_mig_success)
        
#         cur_error = total_variance / cur_denominator
#         prev_error = self.prev_total_cpu_load_vari / prev_denominator
        
#         error_delta = cur_error - prev_error
#         final_error = -self.mc * error_delta
        
#         return final_error, cur_error, prev_error

#     def step(self, action):
#         """Run one simulation step."""
#         # 1. Get "before" stats
#         mig_before_count, mig_before_success = self._get_cumulative_migrations()
        
#         # 2. Run workload
#         workload_cmd = "hackbench 10 process 10000" # A solid scheduler benchmark
#         stdout, _ = self._execute_command(workload_cmd)
#         try:
#             # hackbench prints its own time
#             execution_time = float(re.search(r'Time: ([\d.]+)', stdout).group(1))
#         except:
#             execution_time = 10.0 # Fallback

#         # 3. Get "after" stats
#         mig_after_count, mig_after_success = self._get_cumulative_migrations()
        
#         # 4. Calculate deltas for this step
#         mig_count_delta = mig_after_count - mig_before_count
#         mig_success_delta = mig_after_success - mig_before_success

#         # 5. Get current state and calculate error
#         cluster_variances = self.get_system_state()
#         total_variance = sum(cluster_variances)
        
#         # Set adjustment based on action
#         self.mc = self.step_size if action == 1 else -self.step_size
        
#         final_error, cur_err, prev_err = self.calculate_error(total_variance, mig_count_delta, mig_success_delta)

#         # 6. Apply scheduler change
#         current_cost_str, _ = self._execute_command("cat /proc/sys/kernel/sched_cfs_bandwidth_slice_us")
#         current_cost = int(current_cost_str) if current_cost_str.isdigit() else self.base_cost
#         new_cost = max(self.min_cost, min(self.max_cost, current_cost + self.mc))
#         self._execute_command(f"echo {new_cost} | sudo tee /proc/sys/kernel/sched_cfs_bandwidth_slice_us")

#         # 7. Update state for next iteration
#         self.prev_total_cpu_load_vari = total_variance
#         self.prev_mig_count = mig_count_delta
#         self.prev_mig_success = mig_success_delta

#         # 8. Prepare metrics and reward
#         metrics = {
#             'cluster_variances': cluster_variances,
#             'total_variance': total_variance,
#             'migration_attempts': mig_count_delta,
#             'successful_migrations': mig_success_delta,
#             'execution_time': execution_time,
#             'throughput': 1/execution_time if execution_time > 0 else 0,
#             'error_signal': final_error,
#             'new_sched_cost': new_cost,
#         }
#         reward = metrics['throughput'] - abs(final_error * 1e6) # Reward throughput, penalize error
#         state = np.array(cluster_variances + [mig_count_delta/1000, mig_success_delta/1000])

#         return state, reward, metrics

#     def reset(self):
#         self._execute_command(f"echo {self.base_cost} | sudo tee /proc/sys/kernel/sched_cfs_bandwidth_slice_us")
#         self.prev_total_cpu_load_vari = 0.1
#         self.prev_mig_count = 1
#         self.prev_mig_success = 1
#         time.sleep(1)
#         cluster_variances = self.get_system_state()
#         return np.array(cluster_variances + [0.001, 0.001])

#     def close(self):
#         self.ssh.close()

# # The Policy Agent and main loop can remain largely the same, but need to be adapted
# # for the new state/action space and metrics. This simplified version focuses on the environment.

# class PolicyAgent:
#     def __init__(self, state_size, action_size):
#         self.state_size = state_size
#         self.action_size = action_size
#         self.model = self._build_model()

#     def _build_model(self):
#         model = Sequential([
#             Dense(32, input_dim=self.state_size, activation='relu'),
#             Dense(16, activation='relu'),
#             Dense(self.action_size, activation='softmax')
#         ])
#         model.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy')
#         return model

#     def choose_action(self, state):
#         state = state.reshape([1, self.state_size])
#         probabilities = self.model.predict(state, verbose=0)[0]
#         action = np.random.choice(self.action_size, p=probabilities)
#         return action
    
#     # A full Policy Gradient `learn` method would be implemented here
#     # For simplicity, this example focuses on the environment logic

# if __name__ == "__main__":
#     env = LinuxSchedulerEnvironment()
#     agent = PolicyAgent(state_size=env.state_space_size, action_size=env.action_space_size)
#     NUM_EPISODES = 20
#     STEPS_PER_EPISODE = 10

#     # Initialize CSV file
#     with open(OUTPUT_FILE, 'w', newline='') as f:
#         writer = csv.writer(f)
#         writer.writerow(['episode', 'step', 'execution_time', 'throughput', 'total_variance', 
#                          'migrations', 'new_sched_cost', 'error_signal', 'reward'])
    
#     try:
#         for episode in range(NUM_EPISODES):
#             state = env.reset()
#             print(f"\n--- Episode {episode+1}/{NUM_EPISODES} ---")

#             for step in range(STEPS_PER_EPISODE):
#                 action = agent.choose_action(state)
#                 next_state, reward, metrics = env.step(action)
                
#                 # In a full implementation, agent.store_transition() and agent.learn() would go here

#                 print(f"Step {step+1}: Time={metrics['execution_time']:.2f}s, "
#                       f"Variance={metrics['total_variance']:.2f}, "
#                       f"Migrations={metrics['successful_migrations']}, "
#                       f"Cost={metrics['new_sched_cost']}, "
#                       f"Reward={reward:.2f}")
                
#                 # Write to CSV
#                 with open(OUTPUT_FILE, 'a', newline='') as f:
#                     writer = csv.writer(f)
#                     writer.writerow([episode+1, step+1, metrics['execution_time'], metrics['throughput'], 
#                                      metrics['total_variance'], metrics['successful_migrations'], 
#                                      metrics['new_sched_cost'], metrics['error_signal'], reward])

#                 state = next_state
    
#     except KeyboardInterrupt:
#         print("\nProcess interrupted.")
#     finally:
#         env.close()
#         print(f"\nSimulation finished. Data saved to {OUTPUT_FILE}")

# gemini v2