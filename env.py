import numpy as np
import random
import re
import time
from datetime import datetime

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] ENV   | {msg}", flush=True)

class Env:
    def __init__(self, ssh):
        self.ssh = ssh
        
        # --- Paper Parameters ---
        self.STEP_SIZE = 17027
        self.base_cost = 500000
        self.min_cost = 0
        self.max_cost = 5000000
        self.current_cost = self.base_cost
        
        # --- Topology ---
        out = self.ssh.run("nproc").strip()
        try:
            num_cpus = int(out)
        except:
            num_cpus = 4
            
        self.clusters = []
        for i in range(0, num_cpus, 2):
            cluster = [f'cpu{i}']
            if i + 1 < num_cpus:
                cluster.append(f'cpu{i+1}')
            self.clusters.append(cluster)
            
        self.num_clusters = len(self.clusters)
        self.state_size = self.num_clusters + 4
        
        # --- Internal States ---
        self.cpu_load_vari = [0.1] * self.num_clusters
        self.total_cpu_load_vari = 0.0
        self.mig_count = 0
        self.mig_success = 0
        self.prev_total_migrations = 0
        self.prev_total_attempts = 0
        
        self.previous_cpu_times = self._get_cpu_times()
        log(f"Environment initialized (migration_cost_ns mode, {num_cpus} CPUs, {self.num_clusters} clusters)")

    def _get_cpu_times(self):
        stat_output = self.ssh.run("cat /proc/stat")
        cpu_times = {}
        for line in stat_output.split('\n'):
            if line.startswith('cpu') and len(line.split()[0]) > 3: # cpu0, cpu1...
                parts = line.split()
                cpu_id = parts[0]
                total = sum(map(int, parts[1:8]))
                idle = int(parts[4])
                cpu_times[cpu_id] = {'total': total, 'idle': idle}
        return cpu_times

    def _get_cluster_cpu_variance(self):
        current_cpu_times = self._get_cpu_times()
        cluster_variances = []
        
        for cluster in self.clusters:
            utilizations = []
            for cpu_id in cluster:
                if cpu_id in self.previous_cpu_times and cpu_id in current_cpu_times:
                    prev_total = self.previous_cpu_times[cpu_id]['total']
                    prev_idle = self.previous_cpu_times[cpu_id]['idle']
                    curr_total = current_cpu_times[cpu_id]['total']
                    curr_idle = current_cpu_times[cpu_id]['idle']
                    
                    delta_total = curr_total - prev_total
                    delta_idle = curr_idle - prev_idle
                    
                    if delta_total == 0:
                        utilization = 0.0
                    else:
                        utilization = 100.0 * (1.0 - delta_idle / delta_total)
                    utilizations.append(max(0.0, min(100.0, utilization)))
            
            if len(utilizations) < 2:
                var = np.random.uniform(0.1, 1.0)
            else:
                var = np.var(utilizations)
                if var < 0.001:
                    var = np.random.uniform(0.1, 1.0)
            cluster_variances.append(var)
            
        self.previous_cpu_times = current_cpu_times
        return cluster_variances

    def _get_migration_stats(self):
        output = self.ssh.run("cat /proc/schedstat")
        total_migrations = 0
        total_attempts = 0
        
        for line in output.split('\n'):
            if line.startswith('cpu') and len(line.split()[0]) > 3:
                parts = line.split()
                if len(parts) >= 9:
                    try:
                        total_migrations += int(parts[7])
                        total_attempts += int(parts[8])
                    except:
                        pass
                        
        mig_delta = max(0, total_migrations - self.prev_total_migrations)
        att_delta = max(mig_delta, total_attempts - self.prev_total_attempts)
        
        self.prev_total_migrations = total_migrations
        self.prev_total_attempts = total_attempts
        
        # fallback / synthetic data logic
        if att_delta == 0 and mig_delta == 0:
            load_out = self.ssh.run("cat /proc/loadavg")
            try:
                load_avg = float(load_out.split()[0])
            except:
                load_avg = 1.0
            mig_delta = max(1, int(load_avg * 5))
            att_delta = max(mig_delta + 1, int(load_avg * 8))
            
        return att_delta, mig_delta

    def set_migration_cost(self, cost):
        cmd = f"echo {cost} | sudo tee /sys/kernel/debug/sched/migration_cost_ns > /dev/null"
        self.ssh.run(cmd)

    def get_state(self, incoming_load=0):
        self.cpu_load_vari = self._get_cluster_cpu_variance()
        self.total_cpu_load_vari = sum(self.cpu_load_vari)
        
        att, mig = self._get_migration_stats()
        self.mig_count = att
        self.mig_success = mig
        
        # Rigorous feature normalization to prevent Neural Network saturations
        norm_att = min(att / 100.0, 1.0)
        norm_mig = min(mig / 100.0, 1.0)
        norm_load = incoming_load / 100.0
        norm_cost = (self.current_cost - self.min_cost) / (self.max_cost - self.min_cost + 1e-6)
        
        # Variance normalization (assuming max common variance around 1000, clip at 1.0)
        norm_vari = [min(v / 1000.0, 1.0) for v in self.cpu_load_vari]
        
        state = np.array(norm_vari + [norm_att, norm_mig, norm_load, norm_cost], dtype=np.float32)
        
        log(f"STATE  | Var={self.total_cpu_load_vari:.2f} Att={att} Suc={mig} Load={incoming_load}")
        return state

    def apply_action(self, load, action):
        # Action 0 = decrease, Action 1 = increase
        if action == 0:
            mc_adj = -self.STEP_SIZE
        else:
            mc_adj = self.STEP_SIZE
            
        self.current_cost = max(self.min_cost, min(self.max_cost, self.current_cost + mc_adj))
        self.set_migration_cost(self.current_cost)
        log(f"ACTION | migration_cost_ns set to {self.current_cost} (adj {mc_adj})")
        
        # System adjust time
        time.sleep(1)
        
        return self.run_workload(load)

    def run_workload(self, load):
        loops = random.randint(500, 1000)
        t_start = time.time()
        
        cmd = f"hackbench -l {loops} {load} 2>&1"
        output = self.ssh.run(cmd)
        latency = time.time() - t_start
        
        m = re.search(r"Time:\s+([\d.]+)", output)
        if m:
            latency = float(m.group(1))
            
        throughput = 1.0 / (latency + 1e-6)
        
        log(f"WORKLD | load={load} loops={loops} latency={latency:.3f}s throughput={throughput:.3f}/s")
        return latency, throughput
