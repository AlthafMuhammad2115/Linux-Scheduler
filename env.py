import numpy as np, time

class Env:
    def __init__(self, ssh):
        self.ssh = ssh
        self.prev_ctxt = int(self.ssh.run("grep ctxt /proc/stat").split()[1])
        self.prev_time = time.time()

    def get_state(self, pids, workload):
        cpu_total = float(self.ssh.run("top -bn1 | grep 'Cpu(s)' | awk '{print 100-$8}'"))

        cpu_group, mem_group, nice_vals, max_starve = 0, 0, [], 0
        for pid in pids:
            out = self.ssh.run(f"ps -p {pid} -o %cpu,rss,ni,stat,etimes --no-headers").strip()
            if not out: continue
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

        avg_nice = sum(nice_vals)/len(nice_vals) if nice_vals else 0
        latency = runqueue * 10
        interactivity = 1 if cpu_group < 50 and runqueue < 2 else 0

        return np.array([
            cpu_group, cpu_total, mem_group, mem_free, 0.0,
            runqueue, ctx_rate, avg_nice, max_starve,
            latency, interactivity, workload
        ], dtype=np.float32)

    def apply_action(self, pids, action):
        for pid in pids:
            if action == 0: self.ssh.run(f"sudo renice -n -1 -p {pid}")
            elif action == 2: self.ssh.run(f"sudo renice -n +1 -p {pid}")

    def run_workload(self, load):
        self.ssh.run(f"hackbench {load} &")
