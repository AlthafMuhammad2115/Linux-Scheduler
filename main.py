from ssh_client import SSH
from env import Env
from agent import Agent
import random, time, csv, threading
from datetime import datetime

# ===================== BASIC LOGGER =====================

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

# ===================== CONFIG =====================

VM_IP = "192.168.122.98"
USER  = "oltha"
PASS  = "Drowssap0011#"

USE_RL = True   # <----- TOGGLE THIS

# ===================== SETUP =====================

log("Connecting to VM...")
ssh = SSH(VM_IP, USER, PASS)
env = Env(ssh)
agent = Agent()
log("System initialized.")

# ===================== REWARD FUNCTION =====================

def compute_reward(s, ns, action):
    throughput = ns[0]
    avg_latency = ns[9]
    starvation = ns[8]
    cpu_idle = 100 - ns[1]
    priority_change_cost = abs(action - 1)

    w1, w2, w3, w4, w5 = 1.0, 0.7, 0.8, 0.5, 0.3

    reward = (
        w1 * throughput
        - w2 * avg_latency
        - w3 * starvation
        - w4 * cpu_idle
        - w5 * priority_change_cost
    )

    return reward

# ===================== TRAINING =====================

if USE_RL:
    log("=== TRAINING STARTED ===")

    for ep in range(30):
        log(f"Episode {ep+1}/30 started")

        for step in range(10):
            load = random.choice([1])
            log(f"Step {step+1} | Workload = {load}")

            # Clear previous PIDs before starting new workload
            env.workload_pids = []

            # Run workload in a separate thread so we don't block
            t_workload = threading.Thread(target=env.run_workload, args=(load,))
            t_workload.start()
            
            # Give it a moment to spawn and populate PIDs
            time.sleep(1)

            # Wait for PIDs to be available
            for _ in range(5):
                if env.workload_pids:
                    break
                time.sleep(1)
            
            pids = env.workload_pids
            log(f"EVAL PIDs: {pids}")

 

          
            # Start hackbench if not already running, then try to get PIDs
            # for attempt in range(5):
            #     if attempt == 0: # Only run hackbench on the first attempt
            #         ssh.run("hackbench -l 5000 10 &")
            #         time.sleep(0.5) # Give hackbench a moment to start
                
            #     pids_str = ssh.run("pgrep -f hackbench").strip()
            #     if pids_str:
            #         # Filter out non-numeric output (hackbench sometimes leaks stdout)
            #         pids = [p for p in pids_str.split() if p.isdigit()]
            #         if pids:
            #             break
            #     log(f"Waiting for hackbench... (Attempt {attempt+1}/5)")
            #     time.sleep(1)
            
            # if not pids:
            #     log("WARNING: Could not find hackbench PIDs. Is it installed?")
            #     continue

          
            s = env.get_state(pids, load)

            a = agent.act(s)
            
            env.apply_action(pids, a)
            time.sleep(2)

            ns = env.get_state(pids, load)
            r = compute_reward(s, ns, a)

            log(f"Action = {a} | Reward = {r:.3f}")

            agent.train(s, a, r, ns)
            
            # Enable this if you want to ensure the workload finishes before next step
            t_workload.join()
            
            # Cleanup step to prevent fork bomb
            # ssh.run("pkill hackbench")

        agent.eps *= 0.95
        log(f"Episode {ep+1} completed | New epsilon = {agent.eps:.3f}")

    log("=== TRAINING FINISHED ===")

# ===================== EVALUATION =====================

def evaluate(fname, use_rl):
    log(f"=== EVALUATION STARTED: {fname} ===")

    # 🔥 START WORKLOAD FOR EVALUATION
    load = random.choice([15, 30, 60, 90])  
    env.run_workload(load)
    log(f"EVAL | Started hackbench with load {load}")
    time.sleep(2)   # allow processes to spawn

    start = time.time()

    with open(fname, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(["time","cpu_group","cpu_total","runqueue"])

        while time.time() - start < 300:

            pids_str = ssh.run("pgrep hackbench").strip()
            # Filter out non-numeric output
            pids = [p for p in pids_str.split() if p.isdigit()]
            log(f"EVAL | PIDs: {pids}")

            if not pids:
                log("EVAL | WARNING: No hackbench processes found")
                time.sleep(1)
                continue

            s = env.get_state(pids, load)

            if use_rl:
                a = agent.act(s)
                env.apply_action(pids, a)
                log(f"EVAL | action={a}")

            w.writerow([time.time(), s[0], s[1], s[5]])
            time.sleep(1)

    # 🧹 Cleanup
    ssh.run("pkill hackbench")
    log(f"EVAL | Workload stopped")
    log(f"EVAL | Results saved to {fname}")


# ===================== RUN EVALUATIONS =====================

if USE_RL:
    evaluate("results/with_rl.csv", True)
else:
    evaluate("results/without_rl.csv", False)

log("=== EXPERIMENT COMPLETE ===")
log("Run: python plot.py")
