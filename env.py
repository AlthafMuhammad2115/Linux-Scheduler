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

    def apply_action(self, load, action):
        # Map action to nice value
        # 0 -> High Priority (-5)
        # 1 -> Normal Priority (0)
        # 2 -> Low Priority (5)
        nice_map = {0: -5, 1: 0, 2: 5}
        nice_val = nice_map.get(action, 0)
        
        log(f"ACTION | Launching with Nice {nice_val} (Action {action})")
        return self.run_workload(load, init_nice=nice_val)

    def run_workload(self, load, init_nice=0):
        # Randomize message passing loops between 100 and 5000 as requested
        loops = random.randint(500, 1000)
        # Run in background with specified nice value (priority)
        # Using nice -n ensures the process starts with this priority
        cmd = f"nice -n {init_nice} hackbench -l {loops} {load} > /dev/null 2>&1 & pgrep -f hackbench"
        log(f"WORKLD | hackbench started (bg) with load {load}, loops {loops}, nice {init_nice}")
        return self.ssh.run(cmd).strip()
