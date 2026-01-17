import numpy as np
import random
import time
from datetime import datetime

# ========== SIMPLE TERMINAL LOGGER ==========

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] ENV   | {msg}", flush=True)

# ========== ENVIRONMENT ==========

class Env:
    def __init__(self, ssh):
        self.ssh = ssh
        self.prev_ctxt = int(self.ssh.run("grep ctxt /proc/stat").split()[1])
        self.prev_time = time.time()
        self.workload_pids = []  # Added shared variable
        log("Environment initialized")

    def get_state(self, pids, workload):
        cpu_total = float(self.ssh.run(
            "top -bn1 | grep 'Cpu(s)' | awk '{print 100-$8}'"
        ))

        cpu_group, mem_group, nice_vals, max_starve = 0, 0, [], 0

        for pid in pids:
            out = self.ssh.run(
                f"ps -p {pid} -o %cpu,rss,ni,stat,etimes --no-headers"
            ).strip()

            if not out:
                continue

            cpu, mem, ni, stat, et = out.split()

            cpu_group += float(cpu)
            mem_group += float(mem)
            nice_vals.append(int(ni))

            if 'R' not in stat:
                max_starve = max(max_starve, float(et))

        mem_free = float(self.ssh.run("free -m | awk 'NR==2{print $4}'"))
        runqueue = float(self.ssh.run("cat /proc/loadavg").split()[0])

        now_ctxt = int(self.ssh.run("grep ctxt /proc/stat").split()[1])
        now = time.time()
        ctx_rate = (now_ctxt - self.prev_ctxt) / (now - self.prev_time + 1e-6)
        self.prev_ctxt, self.prev_time = now_ctxt, now

        avg_nice = sum(nice_vals) / len(nice_vals) if nice_vals else 0
        latency = runqueue * 10
        interactivity = 1 if cpu_group < 50 and runqueue < 2 else 0

        state = np.array([
            cpu_group, cpu_total, mem_group, mem_free, ctx_rate,
            runqueue, ctx_rate, avg_nice, max_starve,
            latency, interactivity, workload
        ], dtype=np.float32)

        log(f"STATE  | cpu_grp={cpu_group:.1f} cpu_tot={cpu_total:.1f} "
            f"rq={runqueue:.2f} ctx_rate={ctx_rate:.1f} "
            f"lat={latency:.1f} starve={max_starve:.1f}")

        return state

    def apply_action(self, pids, action):
        if not pids:
            log("ACTION | no PIDs to adjust")
            return

        for pid in pids:
            try:
                # Get current nice value
                current_ni = int(self.ssh.run(f"ps -p {pid} -o ni --no-headers").strip())
                
                new_ni = 0
                if action == 0:   # Boost priority (lower nice value)
                    new_ni = max(-20, current_ni - 1)
                elif action == 2: # Lower priority (higher nice value)
                    new_ni = min(19, current_ni + 1)
                
                if new_ni != current_ni:
                    self.ssh.run(f"sudo renice -n {new_ni} -p {pid}")
            except Exception as e:
                log(f"ACTION | Error setting nice for PID {pid}: {e}")

        log(f"ACTION | Adjust action {action} applied to PIDs {pids}")

    def run_workload(self, load):
        # Randomize message passing loops between 100 and 5000 as requested
        loops = random.randint(100, 500)
        # Removed /usr/bin/ prefix to rely on PATH
        pids_str = self.ssh.run(f"hackbench -l {loops} {load} > /dev/null 2>&1 & pgrep -f hackbench").strip()
        
        # Parse and store PIDs in the shared variable
        self.workload_pids = [p for p in pids_str.split() if p.isdigit()]
        
        # log(f"WORKLD | hackbench started with load {load}, loops {loops}, PIDs: {self.workload_pids}")
        return self.workload_pids
