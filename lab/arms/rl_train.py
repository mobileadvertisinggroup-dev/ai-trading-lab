"""Arm F training — deterministic cross-entropy method (CEM) over a
linear softmax policy on the frozen TradeManagementEnv.

Algorithm choice (recorded as a decision): the project pins no deep-RL
library (requirements.txt has gymnasium only), so Arm F uses a fully
self-contained, dependency-free, DETERMINISTIC trainer: a linear softmax
policy pi(a|s) = softmax(W s + b) with 6x10 + 6 = 66 parameters, trained
by CEM. Every random draw derives from the official seed, so a seed's
training run is bit-reproducible. Greedy (argmax) action selection at
evaluation and in official runs — no sampling at decision time.

The environment itself is a pure function of the trade and its bars
(engine invariants enforced inside), so all stochasticity lives in the
CEM parameter draws — exactly the "deterministic seeds" the spec demands.
"""
from __future__ import annotations

import numpy as np

from lab.arms.rl_env import ACTIONS, OBS_DIM, TradeManagementEnv

N_PARAMS = (OBS_DIM + 1) * len(ACTIONS)


class LinearPolicy:
    def __init__(self, theta: np.ndarray):
        theta = np.asarray(theta, np.float64)
        assert theta.shape == (N_PARAMS,)
        self.theta = theta
        self.W = theta[: OBS_DIM * len(ACTIONS)].reshape(len(ACTIONS),
                                                         OBS_DIM)
        self.b = theta[OBS_DIM * len(ACTIONS):]

    def act(self, obs: np.ndarray) -> int:
        obs = np.nan_to_num(np.asarray(obs, np.float64), nan=0.0,
                            posinf=0.0, neginf=0.0)
        logits = self.W @ obs + self.b
        return int(np.argmax(logits))       # greedy, deterministic


def run_episode(policy: LinearPolicy, trade: dict, bars: list) -> float:
    env = TradeManagementEnv(trade, bars)
    obs, _ = env.reset(seed=0)
    total = 0.0
    while True:
        obs, reward, terminated, truncated, _ = env.step(policy.act(obs))
        total += float(reward)
        if terminated or truncated:
            return total


def evaluate(policy: LinearPolicy, episodes: list[tuple[dict, list]]) -> float:
    if not episodes:
        return 0.0
    return float(np.mean([run_episode(policy, tr, bars)
                          for tr, bars in episodes]))


def train_cem(episodes: list[tuple[dict, list]], seed: int,
              generations: int = 20, population: int = 32,
              elite_frac: float = 0.2, episodes_per_gen: int = 128,
              sigma0: float = 1.0, log=None) -> dict:
    """Returns {theta, seed, history}. Deterministic in (episodes, seed,
    hyperparameters)."""
    rng = np.random.default_rng(seed)
    mu = np.zeros(N_PARAMS)
    sigma = np.full(N_PARAMS, sigma0)
    n_elite = max(1, int(population * elite_frac))
    history = []
    for gen in range(generations):
        # deterministic per-generation episode subsample (without
        # replacement when possible)
        if len(episodes) > episodes_per_gen:
            idx = rng.choice(len(episodes), size=episodes_per_gen,
                             replace=False)
            batch = [episodes[i] for i in idx]
        else:
            batch = episodes
        thetas = mu + sigma * rng.standard_normal((population, N_PARAMS))
        scores = np.array([evaluate(LinearPolicy(th), batch)
                           for th in thetas])
        elite = thetas[np.argsort(scores)[-n_elite:]]
        mu = elite.mean(axis=0)
        sigma = elite.std(axis=0) + 1e-3     # floor keeps exploration alive
        history.append({"gen": gen, "batch": len(batch),
                        "best": float(scores.max()),
                        "mean": float(scores.mean())})
        if log:
            log(f"seed {seed} gen {gen}: best {scores.max():.4f} "
                f"mean {scores.mean():.4f}")
    return {"theta": mu.tolist(), "seed": seed, "history": history,
            "algorithm": "CEM-linear-softmax-v1",
            "hyperparameters": {"generations": generations,
                                "population": population,
                                "elite_frac": elite_frac,
                                "episodes_per_gen": episodes_per_gen,
                                "sigma0": sigma0}}
