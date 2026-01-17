from ssh_client import SSH
from env import Env
from agent import Agent
import random, time, csv
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
            load = random.choice([15,30, 60, 90])
            log(f"Step {step+1} | Workload = {load}")

            # 1. Observe initial system state (before workload)
            # PIDs are empty because we haven't started it yet
            s = env.get_state([], load)

            # 2. Agent chooses action (Priority)
            a = agent.act(s)
            
            # 3. Apply Action: Run workload with chosen nice value
            # This logic is now encapsulated in env.apply_action
            pids_str = env.apply_action(load, a)
            
            # Filter output: keep only digits
            try:
                pids = [p for p in pids_str.split() if p.isdigit()]
            except Exception as e:
                log(f"Error parsing PIDs: {e}")
                pids = []
            
            log(f"EVAL PIDs: {pids}")

            # 4. Wait for effect
            time.sleep(2)

            # 5. Observe resulting state
            ns = env.get_state(pids, load)
            
            # 6. Compute Reward
            r = compute_reward(s, ns, a)
            log(f"Reward = {r:.3f}")

            # 7. Train
            agent.train(s, a, r, ns)
            
            # Cleanup
            # ssh.run("pkill hackbench")

        agent.eps *= 0.95
        log(f"Episode {ep+1} completed | New epsilon = {agent.eps:.3f}")

    log("=== TRAINING FINISHED ===")

# ===================== EVALUATION =====================

def evaluate(fname, use_rl):

    log(f"=== EVALUATION STARTED: {fname} ===")

    start = time.time()

    with open(fname, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(["time","cpu_group","cpu_total","runqueue"])

        while time.time() - start < 300:

            # 1. Get state
            load = random.choice([15, 30, 60, 90])
            s = env.get_state([], load)

            if use_rl:
                # 2. Act
                a = agent.act(s)
                # 3. Apply Action
                pids_str = env.apply_action(load, a)
            
                # Filter output: keep only digits
                try:
                    pids = [p for p in pids_str.split() if p.isdigit()]
                except Exception as e:
                    log(f"Error parsing PIDs: {e}")
                    pids = []
            
                log(f"EVAL PIDs: {pids}")
            else:
                pids_str = env.run_workload(load)
                try:
                    pids = [p for p in pids_str.split() if p.isdigit()]
                except Exception as e:
                    log(f"Error parsing PIDs: {e}")
                    pids = []
                log(f"EVAL PIDs: {pids}")
            
            s = env.get_state(pids, load)
            log(f"EVAL | cpu_grp={s[0]:.1f}")
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
