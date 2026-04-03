import numpy as np
import random
import re
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

        # ---- CPU tick baseline ----
        stat_out = self.ssh.run("cat /proc/stat | grep '^cpu '").strip().split()
        self.prev_user_ticks   = int(stat_out[1])
        self.prev_nice_ticks   = int(stat_out[2])
        self.prev_system_ticks = int(stat_out[3])
        self.prev_idle_ticks   = int(stat_out[4])
        self.prev_total_ticks  = sum(int(x) for x in stat_out[1:])

        # ---- Previous workload performance (used as state features) ----
        self.prev_latency  = 3.0   # seconds – initial guess
        self.prev_wait_frac = 0.5  # fraction 0‑1

        log("Environment initialized (synchronous hackbench mode)")

    # ------------------------------------------------------------------
    # STATE
    #   [0] cpu_user_pct      – % of CPU used by normal-priority processes  (0-100)
    #   [1] cpu_nice_pct      – % of CPU used by niced (positive) processes (0-100) ← action-sensitive
    #   [2] runqueue_scaled   – number of runnable tasks, scaled to 0-100
    #   [3] load_avg_scaled   – 1-min load average, scaled to 0-100
    #   [4] prev_wait_frac    – last hackbench scheduling-wait fraction      (0-100)
    #   [5] prev_latency_norm – last hackbench latency normalised to 0-100
    # ------------------------------------------------------------------

    def get_state(self):
        # 1. CPU time breakdown from /proc/stat
        stat_out = self.ssh.run("cat /proc/stat | grep '^cpu '").strip().split()
        user_ticks   = int(stat_out[1])
        nice_ticks   = int(stat_out[2])
        idle_ticks   = int(stat_out[4])
        total_ticks  = sum(int(x) for x in stat_out[1:])

        d_user  = user_ticks  - self.prev_user_ticks
        d_nice  = nice_ticks  - self.prev_nice_ticks
        d_idle  = idle_ticks  - self.prev_idle_ticks
        d_total = total_ticks - self.prev_total_ticks + 1e-6

        cpu_user  = (d_user / d_total) * 100.0   # normal-prio CPU share
        cpu_nice  = (d_nice / d_total) * 100.0   # niced CPU share ← changes with action
        cpu_idle  = (d_idle / d_total) * 100.0
        cpu_busy  = 100.0 - cpu_idle               # total busy%

        self.prev_user_ticks  = user_ticks
        self.prev_nice_ticks  = nice_ticks
        self.prev_idle_ticks  = idle_ticks
        self.prev_total_ticks = total_ticks

        # 2. Load average + runqueue length
        loadavg_str = self.ssh.run("cat /proc/loadavg").strip().split()
        load_avg  = float(loadavg_str[0])
        runqueue  = float(loadavg_str[3].split('/')[0])

        state = np.array([
            cpu_user,              # [0] cpu_user %       (0-100)
            cpu_nice,              # [1] cpu_nice %       (0-100) ← action-sensitive
            runqueue,              # [2] runqueue length  (raw count)
            load_avg,              # [3] 1-min load avg   (raw float)
            self.prev_wait_frac,   # [4] scheduling wait  (0-1)
            self.prev_latency,     # [5] last latency     (seconds)
        ], dtype=np.float32)

        log(f"STATE  | usr={cpu_user:.1f}% nice={cpu_nice:.1f}% "
            f"rq={runqueue} load={load_avg:.2f} "
            f"prev_wait={self.prev_wait_frac:.2f} prev_lat={self.prev_latency:.2f}s")

        return state

    # ------------------------------------------------------------------
    # ACTION → runs hackbench synchronously, returns (latency, throughput, responsiveness)
    # ------------------------------------------------------------------

    def apply_action(self, load, action):
        nice_map = {0: -5, 1: 0, 2: 5}
        nice_val = nice_map.get(action, 0)
        log(f"ACTION | Nice={nice_val} (action={action})")
        return self.run_workload(load, init_nice=nice_val)

    def run_workload(self, load, init_nice=0):
        loops = random.randint(500, 1000)

        # --- Sample CPU ticks BEFORE workload ---
        stat_before = self.ssh.run("cat /proc/stat | grep '^cpu '").strip().split()
        total_before = sum(int(x) for x in stat_before[1:])
        idle_before  = int(stat_before[4])

        t_start = time.time()

        # Run synchronously (no &) so we can capture hackbench output
        cmd = f"sudo nice -n {init_nice} hackbench -l {loops} {load} 2>&1"
        output = self.ssh.run(cmd)
        latency_wall = time.time() - t_start   # wall-clock fallback

        # --- Sample CPU ticks AFTER workload ---
        stat_after = self.ssh.run("cat /proc/stat | grep '^cpu '").strip().split()
        total_after = sum(int(x) for x in stat_after[1:])
        idle_after  = int(stat_after[4])

        d_total = total_after - total_before + 1e-6
        d_idle  = idle_after  - idle_before

        # Approximate scheduling-wait fraction for hackbench:
        #   fraction of real time the CPU was NOT idle (busy on workload or contention)
        cpu_busy_frac = 1.0 - (d_idle / d_total)
        # wait_frac: how much time the system spent waiting rather than usefully executing
        # Higher cpu_busy → system was saturated → more scheduling wait
        wait_frac = max(0.0, cpu_busy_frac - 0.5) * 2.0   # non-linear amplification

        # Parse hackbench's "Time: X.XX" line
        m = re.search(r"Time:\s+([\d.]+)", output)
        latency = float(m.group(1)) if m else latency_wall

        # Derived metrics
        throughput      = 1.0 / (latency + 1e-6)          # tasks per second
        responsiveness  = 1.0 / (1.0 + wait_frac) * 100.0 # 0-100, higher = more responsive

        # Store for next get_state() call
        self.prev_latency   = latency
        self.prev_wait_frac = wait_frac

        log(f"WORKLD | nice={init_nice} load={load} loops={loops} "
            f"latency={latency:.3f}s throughput={throughput:.3f}/s "
            f"wait_frac={wait_frac:.3f} responsiveness={responsiveness:.1f}")

        return latency, throughput, responsiveness
