"""Arms B/C/E training-pipeline shells (SPEC FINAL-1.2 §3).

Runnable end-to-end on synthetic data; NO performance is claimed anywhere.
Hyperparameters, thresholds, and mappings are DRAFT stubs — the real values
are selected on training+validation only and frozen before holdout
(spec §3, §22). LightGBM per §27.

Structural leak guards (deliberate-leak fixtures assert these FAIL loudly):

1. `FORBIDDEN_COLUMNS` — a feature matrix containing label/outcome columns
   is refused.
2. `validate_split` — fitting is refused unless every training example's
   information interval ends before the validation boundary (a purge
   violation cannot reach a model).
3. Feature names must come from the DATA_DICTIONARY (F01–F28) — unknown
   columns are refused, so an improvised feature cannot slip in unreviewed.
"""
from __future__ import annotations

import numpy as np

import lightgbm as lgb

FORBIDDEN_COLUMNS = {"net_r", "net_pnl", "label", "target", "exit_t",
                     "realized_pnl", "pnl", "info_interval", "outcome"}
ALLOWED_PREFIXES = tuple(f"F{i:02d}_" for i in range(1, 29))
E_BUCKETS = (0.25, 0.50, 0.75, 1.00)


class LeakError(RuntimeError):
    """A structural leak guard fired — this is a bug upstream, never
    something to silence."""


def validate_columns(feature_names: list[str]) -> None:
    bad = [c for c in feature_names
           if c.split("_")[0].lower() in {f.split("_")[0] for f in ()}
           or c.lower() in FORBIDDEN_COLUMNS
           or any(f in c.lower() for f in FORBIDDEN_COLUMNS)]
    if bad:
        raise LeakError(f"label/outcome columns in features: {bad}")
    unknown = [c for c in feature_names
               if not c.startswith(ALLOWED_PREFIXES)]
    if unknown:
        raise LeakError(f"columns outside DATA_DICTIONARY F01-F28: {unknown}")


def validate_split(train_examples: list[dict], val_start_ms: int) -> None:
    """Every training example's full information interval must end strictly
    before the validation boundary (spec §10)."""
    for ex in train_examples:
        lo, hi = ex["info_interval"]
        if hi >= val_start_ms:
            raise LeakError(
                f"purge violation: training example at t={ex['t']} has "
                f"info interval ending {hi} >= val_start {val_start_ms}")


def _matrix(examples: list[dict], feature_names: list[str]) -> np.ndarray:
    validate_columns(feature_names)
    return np.array([[ex["features"][c] for c in feature_names]
                     for ex in examples], dtype=np.float64)


_LGB_DRAFT = dict(n_estimators=100, max_depth=4, learning_rate=0.05,
                  subsample=0.8, colsample_bytree=0.8, verbose=-1)


class FilterPipeline:
    """Arm B: accept/reject. Binary target: net_r > 0."""
    version = "B-lgbm-draft"

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold          # DRAFT; frozen pre-holdout
        self.model = None
        self.feature_names: list[str] | None = None

    def fit(self, train_examples, feature_names, val_start_ms):
        validate_split(train_examples, val_start_ms)
        X = _matrix(train_examples, feature_names)
        y = np.array([ex["net_r"] > 0 for ex in train_examples], dtype=int)
        self.model = lgb.LGBMClassifier(**_LGB_DRAFT)
        self.model.fit(X, y)
        self.feature_names = list(feature_names)
        return self

    def accept(self, cand, features):
        X = np.array([[features[c] for c in self.feature_names]])
        prob = float(self.model.predict_proba(X)[0, 1])
        return prob >= self.threshold, prob


class RankerPipeline:
    """Arm C: relative ranking via net-R regression score (never displayed
    as 'confidence' — reported as 'ranked i of n')."""
    version = "C-lgbm-draft"

    def __init__(self):
        self.model = None
        self.feature_names = None

    def fit(self, train_examples, feature_names, val_start_ms):
        validate_split(train_examples, val_start_ms)
        X = _matrix(train_examples, feature_names)
        y = np.array([ex["net_r"] for ex in train_examples])
        self.model = lgb.LGBMRegressor(**_LGB_DRAFT)
        self.model.fit(X, y)
        self.feature_names = list(feature_names)
        return self

    def score(self, cand, features):
        X = np.array([[features[c] for c in self.feature_names]])
        return float(self.model.predict(X)[0])


class SizerPipeline:
    """Arm E: net-R regression mapped into the four frozen buckets.
    DRAFT mapping: prediction quartiles over the TRAINING distribution ->
    0.25/0.50/0.75/1.00; the real bucket mapping is selected on
    train+validation with the frozen §3 utility and frozen pre-holdout."""
    version = "E-lgbm-draft"

    def __init__(self):
        self.model = None
        self.feature_names = None
        self._cuts: np.ndarray | None = None

    def fit(self, train_examples, feature_names, val_start_ms):
        validate_split(train_examples, val_start_ms)
        X = _matrix(train_examples, feature_names)
        y = np.array([ex["net_r"] for ex in train_examples])
        self.model = lgb.LGBMRegressor(**_LGB_DRAFT)
        self.model.fit(X, y)
        preds = self.model.predict(X)
        self._cuts = np.quantile(preds, [0.25, 0.5, 0.75])
        self.feature_names = list(feature_names)
        return self

    def bucket(self, cand, features):
        X = np.array([[features[c] for c in self.feature_names]])
        p = float(self.model.predict(X)[0])
        b = E_BUCKETS[int(np.searchsorted(self._cuts, p))]
        assert b in E_BUCKETS and b > 0     # Arm E may never choose zero
        return b
