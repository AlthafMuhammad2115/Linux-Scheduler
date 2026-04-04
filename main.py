from ssh_client import SSH
from env import Env
from agent import Agent
import random, time, csv
from datetime import datetime

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] main  | {msg}", flush=True)

# ===================== CONFIG =====================

VM_IP = "192.168.122.155"
USER  = "oltha"
PASS  = "Drowssap0011#"

USE_RL      = False   
TRAIN_MODE  = False    

# ===================== SETUP =====================

log("Connecting to VM...")
ssh = SSH(VM_IP, USER, PASS)
env = Env(ssh)
agent = Agent(state_dim=env.state_size, action_dim=2)
log("System initialized.")

# ===================== REWARD FUNCTION =====================

def compute_reward(env_obj, latency, throughput):
    # Error formula derived from Han & Lee paper: Total Variance / (Attempts + Successes)
    cur_error = env_obj.total_cpu_load_vari / max(5, env_obj.mig_count + env_obj.mig_success)
    
    base_reward = throughput * 10.0
    error_penalty = abs(cur_error) / 10.0
    efficiency_bonus = (env_obj.mig_success / max(1, env_obj.mig_count))
    variance_penalty = env_obj.total_cpu_load_vari / 100.0
    
    reward = base_reward - error_penalty + efficiency_bonus - variance_penalty
    return reward

# ===================== TRAINING =====================

if USE_RL and TRAIN_MODE:
    log("=== TRAINING STARTED ===")

    with open("results/training_logs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["episode", "cumulative_reward", "average_reward", "average_loss"])

        for ep in range(100):
            log(f"Episode {ep+1}/100 started")
            ep_reward  = 0
            ep_loss    = 0
            ep_lat     = 0
            ep_tput    = 0
            ep_mig     = 0
            train_steps = 0

            for step in range(15):
                load = random.choice([15, 30, 60, 90])
                log(f"Step {step+1} | Workload = {load}")

                # Agent observes the state factoring in the incoming random workload
                s = env.get_state(incoming_load=load)
                a = agent.act(s)
                
                # Apply migration cost adjustment
                latency, throughput = env.apply_action(load, a)

                # Next state observes the resolved state after the workload
                ns = env.get_state(incoming_load=0)

                r = compute_reward(env, latency, throughput)
                ep_reward += r
                ep_lat    += latency
                ep_tput   += throughput
                ep_mig    += env.current_cost
                log(f"Reward={r:.3f} | lat={latency:.2f}s tput={throughput:.3f}/s mc={env.current_cost}")

                loss = agent.train(s, a, r, ns)
                if loss > 0:
                    ep_loss    += loss
                    train_steps += 1

            agent.eps *= 0.95

            avg_reward = ep_reward  / 15
            avg_loss   = ep_loss    / train_steps if train_steps > 0 else 0.0
            avg_lat    = ep_lat     / 15
            avg_tput   = ep_tput    / 15
            avg_mig    = ep_mig     / 15

            w.writerow([ep+1, ep_reward, avg_reward, avg_loss])
            f.flush()
            log(f"Episode {ep+1} done | eps={agent.eps:.3f} | reward={ep_reward:.2f} | loss={avg_loss:.4f}")

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
        w.writerow(["time", "action", "migration_cost",
                    "latency", "throughput", "cpu_variance",
                    "mig_attempts", "mig_successes", "reward"])

        while time.time() - start < 300:
            load = random.choice([15, 30, 60, 90])

            s = env.get_state(incoming_load=load)

            if use_rl:
                a = agent.act(s)
                latency, throughput = env.apply_action(load, a)
            else:
                a = -1 # No action taken
                latency, throughput = env.run_workload(load)

            r = compute_reward(env, latency, throughput)

            elapsed = time.time() - start
            w.writerow([
                round(elapsed, 2),
                a,
                env.current_cost,
                round(latency, 4),
                round(throughput, 6),
                round(env.total_cpu_load_vari, 2),
                env.mig_count,
                env.mig_success,
                round(r, 4)
            ])
            f.flush()

            log(f"EVAL | lat={latency:.2f}s tput={throughput:.3f}/s mc={env.current_cost}")

    ssh.run("pkill hackbench 2>/dev/null; true")
    log(f"EVAL | Results saved to {fname}")


# ===================== RUN =====================

if USE_RL:
    evaluate("results/with_rl.csv", True)
else:
    evaluate("results/without_rl.csv", False)

log("=== EXPERIMENT COMPLETE ===")
log("Run: python plot.py")
