"""Arm F SB3 policy adapter — canonical obs-v2 in, protocol action out.

The SAME adapter serves orchestrator inference (competition.rl_policy) and
the shakedown's frozen-policy wiring: it consumes the canonical
lab.arms.observation vector unchanged (no padding, no re-mapping — the
zero-padding FrozenRLPolicy of shakedown run 1/2 is retired with SD-RLOBS)
and returns the protocol action name via deterministic prediction.
"""
from __future__ import annotations

import numpy as np

from lab.arms.observation import OBS_DIM, OBS_SCHEMA_HASH, OBS_SCHEMA_VERSION
from lab.arms.rl_env import ACTIONS


class SB3PolicyAdapter:
    def __init__(self, model, version: str):
        self.model = model
        self.version = version
        self.obs_schema = {"version": OBS_SCHEMA_VERSION,
                           "hash": OBS_SCHEMA_HASH}

    def action_from_obs(self, obs) -> str:
        v = np.asarray(obs, np.float32)
        if v.shape != (OBS_DIM,):
            raise ValueError(f"obs must be canonical {OBS_DIM}-dim, "
                             f"got {v.shape}")   # never pad, never truncate
        a, _ = self.model.predict(v, deterministic=True)
        return ACTIONS[int(a)]


def load_policy(path: str, version: str | None = None) -> SB3PolicyAdapter:
    from stable_baselines3 import PPO
    model = PPO.load(path, device="cpu")
    return SB3PolicyAdapter(model, version or f"arm_f_sb3_ppo:{path}")
