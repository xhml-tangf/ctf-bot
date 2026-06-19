import optuna
import subprocess
import os
import re
import sys
import time
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config

BOT_NAMES = ["tang_fuqing", "wang_simu", "ling_jiayou"]

SEARCH_SPACE = {
    "REPULSION_A": ("float", 3.0, 15.0, True),
    "REPULSION_B_FRAC": ("float", 0.2, 0.8, False),
    "WAYPOINT_REACH": ("float", 1.0, 2.5, False),
    "RECOMPUTE_DT": ("float", 0.2, 1.0, False),
    "TICK_DT": ("float", 0.03, 0.1, False),
    "HONEY_COST": ("float", 1.5, 4.0, False),
    "THREAT_COST_K": ("float", 0.5, 3.0, False),
    "BLOCK_WEIGHT": ("float", 0.5, 3.0, False),
    "NEAR_DOUBLED": ("float", 1.0, 3.5, False),
    "MOOSHROOM_R": ("float", 2.0, 5.0, False),
    "SILVERFISH_R": ("float", 4.0, 8.0, False),
    "ENEMY_R_STEAL": ("float", 3.0, 8.0, False),
    "KITE_DIST": ("float", 1.0, 3.5, False),
    "CATCH_NEAR": ("float", 0.5, 2.0, False),
    "DEPOSIT_NEAR": ("float", 2.0, 6.0, False),
}


def kill_stale():
    try:
        subprocess.run(
            'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name=\\\'python.exe\\\'\\" | Where-Object { $_.CommandLine -match \'main.py\' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"',
            shell=True, capture_output=True, timeout=5
        )
    except Exception:
        pass
    time.sleep(1)


def run_match(params, timeout=225):
    full = dict(config.DEFAULT_PARAMS)
    full.update(params)
    config.save_params(full)
    kill_stale()

    env = {**os.environ,
           "CTF_PLAYERS": ",".join(BOT_NAMES),
           "CTF_ENEMY": "trivial",
           "CTF_MAP": "random",
           "PYTHONUTF8": "1"}

    t0 = time.time()
    try:
        proc = subprocess.run(
            ["python", "-u", os.path.join(HERE, "main.py")],
            capture_output=True, text=True, timeout=timeout, env=env
        )
        output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as e:
        out = e.stdout if e.stdout else b""
        err = e.stderr if e.stderr else b""
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", errors="replace")
        output = out + err
    except Exception:
        return -8, "", 0

    dur = time.time() - t0

    our_pickups = 0
    our_submits = 0
    our_infected = 0
    for name in BOT_NAMES:
        our_pickups += len(re.findall(rf'\[{re.escape(name)}\].*pickup', output))
        our_submits += len(re.findall(rf'\[{re.escape(name)}\].*submit', output))
        our_infected += len(re.findall(rf'\[{re.escape(name)}\].*INFECTED', output))

    enemy_score = 0
    for line in output.split('\n'):
        low = line.lower()
        if any(name in line for name in BOT_NAMES):
            continue
        if any(kw in low for kw in ['captured', 'scored', 'flag taken',
                                     'capture', 'team left', 'team right']):
            enemy_score += 1

    our_score = 0
    for name in BOT_NAMES:
        scores = re.findall(rf'\[{re.escape(name)}\].*?score (\d+)/8', output)
        if scores:
            our_score += int(scores[-1])

    reward = our_pickups * 2 + our_submits * 5 - our_infected * 1 - enemy_score * 3
    if our_score >= 8:
        reward += 10
    elif dur < 185:
        reward -= 10

    return reward, output, dur


def objective(trial):
    params = {}
    for name, (ptype, lo, hi, is_log) in SEARCH_SPACE.items():
        if ptype == "float":
            params[name] = trial.suggest_float(name, lo, hi, log=is_log)
        elif ptype == "int":
            params[name] = trial.suggest_int(name, lo, hi)

    print(f"[trial] running...", flush=True)
    reward, output, dur = run_match(params)
    trial.set_user_attr("reward", reward)
    trial.set_user_attr("dur", round(dur, 1))
    tail = output[-300:] if output else ""
    trial.set_user_attr("tail", tail)
    return reward


def main():
    n_trials = 25
    print(f"=== 3v3 vs trivial | {n_trials} trials | 15 params ===")
    print(f"Estimated: {n_trials} x ~3.5min = {n_trials*3.5:.0f} min")

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        storage="sqlite:///" + os.path.join(HERE, "optuna.db"),
        study_name="3v3_trivial",
        load_if_exists=True
    )

    start = time.time()
    for i in range(n_trials):
        ts = time.time()
        study.optimize(objective, n_trials=1)
        dt = time.time() - ts
        elapsed = time.time() - start
        remaining = (n_trials - i - 1) * dt
        val = study.trials[-1].value
        best = study.best_value if study.best_value is not None else "?"
        print(f"[{i+1}/{n_trials}] reward={val:.1f} best={best} "
              f"dt={dt:.0f}s ETA={remaining/60:.1f}min")

        if study.best_value is not None:
            final = dict(config.DEFAULT_PARAMS)
            final.update(study.best_params)
            config.save_params(final)

    print("\n=== DONE ===")
    print(f"Best reward: {study.best_value}")
    print(f"Best params: {json.dumps(study.best_params, indent=2)}")
    try:
        imp = optuna.importance.get_param_importances(study)
        print("\nParam importances:")
        for k, v in sorted(imp.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v:.4f}")
    except Exception:
        pass
    print("\nBest params saved to params.json")


if __name__ == "__main__":
    main()
