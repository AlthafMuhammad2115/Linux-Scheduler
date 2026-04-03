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

VM_IP = "192.168.122.155"
USER  = "oltha"
PASS  = "Drowssap0011#"

USE_RL      = True   # <----- TOGGLE THIS
TRAIN_MODE  = True    # <----- Set to True to train, False to just load and evaluate

# ===================== SETUP =====================

log("Connecting to VM...")
ssh = SSH(VM_IP, USER, PASS)
env = Env(ssh)
agent = Agent()
log("System initialized.")

# ===================== REWARD FUNCTION =====================
#
# State vector (6 features):
#   [0] cpu_user_pct      – normal-prio CPU %          (0-100)
#   [1] cpu_nice_pct      – niced-prio CPU %            (0-100) ← action-sensitive
#   [2] runqueue_scaled   – runnable tasks              (0-100)
#   [3] load_avg_scaled   – 1-min load avg              (0-100)
#   [4] prev_wait_frac    – last scheduling-wait %      (0-100)
#   [5] prev_latency_norm – last hackbench latency ×10  (0-100)
#
# Target: maximise THROUGHPUT (minimise hackbench latency)
#         + maximise RESPONSIVENESS (minimise scheduling wait)

def compute_reward(latency, throughput, responsiveness, action):
    # Throughput reward: higher is better.
    # 1/latency scaled so latency=1s → ~10, latency=5s → ~2, latency=10s → ~1
    throughput_reward = (1.0 / (latency + 1e-6)) * 10.0

    # Responsiveness bonus: 0-100 → scaled 0-10
    responsiveness_bonus = responsiveness / 10.0

    # Small cost for deviating from default (action 1 = nice 0)
    priority_cost = abs(action - 1) * 0.1

    reward = throughput_reward + 0.3 * responsiveness_bonus - priority_cost
    return reward


# ===================== TRAINING =====================

if USE_RL and TRAIN_MODE:
    log("=== TRAINING STARTED ===")

    with open("results/training_logs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["episode", "cumulative_reward", "average_reward", "average_loss",
                    "epsilon", "avg_latency", "avg_throughput", "avg_responsiveness"])

        for ep in range(100):
            log(f"Episode {ep+1}/100 started")
            ep_reward  = 0
            ep_loss    = 0
            ep_lat     = 0
            ep_tput    = 0
            ep_resp    = 0
            train_steps = 0

            for step in range(15):
                load = random.choice([15, 30, 60, 90])
                log(f"Step {step+1} | Workload = {load}")

                # 1. Observe state BEFORE workload
                s = env.get_state()

                # 2. Agent chooses action (nice value)
                a = agent.act(s)

                # 3. Run workload synchronously – returns hackbench metrics
                latency, throughput, responsiveness = env.apply_action(load, a)

                # 4. Observe state AFTER workload (now includes prev_latency & wait_frac)
                ns = env.get_state()

                # 5. Compute reward
                r = compute_reward(latency, throughput, responsiveness, a)
                ep_reward += r
                ep_lat    += latency
                ep_tput   += throughput
                ep_resp   += responsiveness
                log(f"Reward={r:.3f} | lat={latency:.2f}s tput={throughput:.3f}/s resp={responsiveness:.1f}")

                # 6. Train
                loss = agent.train(s, a, r, ns)
                if loss > 0:
                    ep_loss    += loss
                    train_steps += 1

            agent.eps *= 0.95

            avg_reward = ep_reward  / 15
            avg_loss   = ep_loss    / train_steps if train_steps > 0 else 0.0
            avg_lat    = ep_lat     / 15
            avg_tput   = ep_tput    / 15
            avg_resp   = ep_resp    / 15

            w.writerow([ep+1, ep_reward, avg_reward, avg_loss,
                        agent.eps, avg_lat, avg_tput, avg_resp])
            f.flush()
            log(f"Episode {ep+1} done | eps={agent.eps:.3f} | "
                f"reward={ep_reward:.2f} lat={avg_lat:.2f}s "
                f"tput={avg_tput:.3f}/s resp={avg_resp:.1f}")

    log("=== TRAINING FINISHED ===")
    agent.save("rl_model.pth")


# ===================== EVALUATION =====================

def evaluate(fname, use_rl):
    log(f"=== EVALUATION STARTED: {fname} ===")

    if use_rl:
        agent.load("rl_model.pth")
        agent.eps = 0.0   # pure exploitation

    start = time.time()

    with open(fname, 'w', newline='') as f:
        w = csv.writer(f)
        # Columns for plotting throughput & responsiveness
        w.writerow(["time", "action", "nice_val",
                    "latency", "throughput", "responsiveness",
                    "cpu_user", "cpu_nice", "runqueue", "load_avg",
                    "wait_frac"])

        while time.time() - start < 300:
            load = random.choice([15, 30, 60, 90])

            # Get state
            s = env.get_state()

            if use_rl:
                a = agent.act(s)
                latency, throughput, responsiveness = env.apply_action(load, a)
            else:
                a = 1   # default nice=0 baseline
                latency, throughput, responsiveness = env.run_workload(load, init_nice=0)

            nice_map = {0: -5, 1: 0, 2: 5}
            nice_val = nice_map.get(a, 0)

            # cpu_user=s[0], cpu_nice=s[1], runqueue=s[2]/5, load=s[3]/12.5
            elapsed = time.time() - start
            w.writerow([
                round(elapsed, 2),
                a,
                nice_val,
                round(latency, 4),
                round(throughput, 6),
                round(responsiveness, 2),
                round(float(s[0]), 2),          # cpu_user
                round(float(s[1]), 2),          # cpu_nice
                round(float(s[2]) / 5.0, 2),   # runqueue (unscaled)
                round(float(s[3]) / 12.5, 4),  # load_avg (unscaled)
                round(env.prev_wait_frac, 4),
            ])
            f.flush()

            log(f"EVAL | lat={latency:.2f}s tput={throughput:.3f}/s "
                f"resp={responsiveness:.1f} nice={nice_val}")

    ssh.run("pkill hackbench 2>/dev/null; true")
    log(f"EVAL | Results saved to {fname}")


# ===================== RUN EVALUATIONS =====================

if USE_RL:
    evaluate("results/with_rl.csv", True)
else:
    evaluate("results/without_rl.csv", False)

log("=== EXPERIMENT COMPLETE ===")
log("Run: python plot.py")
