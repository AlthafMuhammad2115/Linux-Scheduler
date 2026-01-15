from ssh_client import SSH
from env import Env
from agent import Agent
import random, time, csv

VM_IP="192.168.122.98"
USER="oltha"
PASS="Drowssap0011#"

USE_RL = True   # <--- toggle this only

ssh = SSH(VM_IP,USER,PASS)
env = Env(ssh)
agent = Agent()

def compute_reward(s, ns, action):
    # Extract needed metrics
    throughput = ns[0]                         # cpu_group
    avg_latency = ns[9]                        # latency estimate
    starvation = ns[8]                        # max_starvation
    cpu_idle = 100 - ns[1]                    # cpu_total
    priority_change_cost = abs(action - 1)    # 0 if no change, 1 otherwise

    # Weights (you can tune these)
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
    for ep in range(30):
        for _ in range(10):
            load = random.choice([10,50,100,200])
            env.run_workload(load)
            time.sleep(1)

            pids = ssh.run("pgrep hackbench").split()
            s = env.get_state(pids,load)

            a = agent.act(s)
            env.apply_action(pids,a)

            time.sleep(2)
            ns = env.get_state(pids,load)
            r = compute_reward(s, ns, a)
            agent.train(s, a, r, ns)
            # agent.train(s,a,ns[0],ns)

        agent.eps *= 0.95

# ===================== EVALUATION =====================

def evaluate(fname, use_rl):
    start=time.time()
    with open(fname,'w',newline='') as f:
        w=csv.writer(f)
        w.writerow(["time","cpu_group","cpu_total","runqueue"])

        while time.time()-start < 300:
            pids = ssh.run("pgrep hackbench").split()
            s = env.get_state(pids,0)

            if use_rl:                     # <<< CRITICAL FIX
                a = agent.act(s)
                env.apply_action(pids,a)

            w.writerow([time.time(),s[0],s[1],s[5]])
            time.sleep(1)

if USE_RL:
    evaluate("results/with_rl.csv", True)
    evaluate("results/without_rl.csv", False)
else:
    evaluate("results/without_rl.csv", False)

print("Experiment complete. Run: python plot.py")
