from dataclasses import dataclass
from hashlib import sha256
import json


def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def citcom_style_ate(run_system, adjustment, treatment_key, control_value, treatment_value, repeats):
    control_cfg = {**adjustment, treatment_key: control_value}
    treatment_cfg = {**adjustment, treatment_key: treatment_value}
    controls = [run_system(control_cfg)["Y"] for _ in range(repeats)]
    treatments = [run_system(treatment_cfg)["Y"] for _ in range(repeats)]
    return sum(t - c for c, t in zip(controls, treatments)) / repeats


class PureSUT:
    def __call__(self, cfg):
        return {"Y": cfg["X"] * 2}


class StatefulDriftSUT:
    def __init__(self):
        self.i = 0

    def __call__(self, cfg):
        y = cfg["X"] * 2 + self.i
        self.i += 1
        return {"Y": y}


@dataclass(frozen=True)
class Arm:
    causal_probe_id: str
    role: str
    non_broadcast_input_digest: str
    generation: int
    frame_version: int
    pre_state_digest: str
    downstream_output_digest: str
    broadcast_id: str | None
    recipient_ids: tuple[str, ...]
    uptaken_recipient_ids: tuple[str, ...]


@dataclass(frozen=True)
class Probe:
    control: Arm
    intervention: Arm
    sham_control_output_digest: str


def adjudicate(p: Probe):
    c, i = p.control, p.intervention
    if c.causal_probe_id != i.causal_probe_id:
        return "INESTIMABLE", "PAIR_ID_MISMATCH"
    if c.non_broadcast_input_digest != i.non_broadcast_input_digest:
        return "INESTIMABLE", "FROZEN_INPUT_MISMATCH"
    if (c.generation, c.frame_version) != (i.generation, i.frame_version):
        return "INESTIMABLE", "GENERATION_OR_FRAME_MISMATCH"
    if c.pre_state_digest != i.pre_state_digest:
        return "INESTIMABLE", "ORDER_STATE_CONTAMINATION"
    if c.broadcast_id is not None or i.broadcast_id is None:
        return "INESTIMABLE", "INTERVENTION_IDENTITY_INVALID"
    if set(i.uptaken_recipient_ids) != set(i.recipient_ids):
        return "INESTIMABLE", "RECIPIENT_UPTAKE_INCOMPLETE"
    if p.sham_control_output_digest != c.downstream_output_digest:
        return "INESTIMABLE", "SHAM_CONTROL_DRIFT"
    if c.downstream_output_digest == i.downstream_output_digest:
        return "NEGATIVE", "NO_DOWNSTREAM_CHANGE"
    return "POSITIVE", "MATCHED_CAUSAL_DIFFERENCE"


def arm(
    role,
    out,
    *,
    probe="p1",
    input_d="inputA",
    pre="stateA",
    bcast=None,
    recipients=(),
    uptake=(),
    generation=3,
    frame=7,
):
    return Arm(
        probe,
        role,
        input_d,
        generation,
        frame,
        pre,
        digest(out),
        bcast,
        tuple(recipients),
        tuple(uptake),
    )


# Source-derived CITCOM treatment/control reproduction: the pinned upstream test uses Y=2X.
pure_ate = citcom_style_ate(PureSUT(), {}, "X", 1, 2, 200)
assert pure_ate == 2.0

# Counterexample: blockwise control-then-treatment execution on a stateful target confounds treatment with drift.
drift_ate = citcom_style_ate(StatefulDriftSUT(), {}, "X", 1, 2, 3)
assert drift_ate == 5.0, drift_ate

base_c = arm("CONTROL", {"Y": 2}, bcast=None)
base_i = arm(
    "INTERVENTION",
    {"Y": 4},
    bcast="b1",
    recipients=("r1", "r2"),
    uptake=("r1", "r2"),
)

cases = {}

cases["matched_positive"] = adjudicate(Probe(base_c, base_i, base_c.downstream_output_digest))
assert cases["matched_positive"] == ("POSITIVE", "MATCHED_CAUSAL_DIFFERENCE")

i = arm(
    "INTERVENTION",
    {"Y": 4},
    input_d="inputB",
    bcast="b1",
    recipients=("r1", "r2"),
    uptake=("r1", "r2"),
)
cases["mismatched_frozen_input"] = adjudicate(Probe(base_c, i, base_c.downstream_output_digest))
assert cases["mismatched_frozen_input"][0] == "INESTIMABLE"

i = arm(
    "INTERVENTION",
    {"Y": 4},
    bcast="b1",
    recipients=("r1", "r2"),
    uptake=("r1",),
)
cases["incomplete_recipient_uptake"] = adjudicate(Probe(base_c, i, base_c.downstream_output_digest))
assert cases["incomplete_recipient_uptake"][0] == "INESTIMABLE"

cases["sham_control_drift"] = adjudicate(Probe(base_c, base_i, digest({"Y": 3})))
assert cases["sham_control_drift"][0] == "INESTIMABLE"

i = arm(
    "INTERVENTION",
    {"Y": 4},
    pre="stateB",
    bcast="b1",
    recipients=("r1", "r2"),
    uptake=("r1", "r2"),
)
cases["order_state_contamination"] = adjudicate(Probe(base_c, i, base_c.downstream_output_digest))
assert cases["order_state_contamination"][0] == "INESTIMABLE"

i = arm(
    "INTERVENTION",
    {"Y": 2},
    bcast="b1",
    recipients=("r1", "r2"),
    uptake=("r1", "r2"),
)
cases["matched_no_effect"] = adjudicate(Probe(base_c, i, base_c.downstream_output_digest))
assert cases["matched_no_effect"] == ("NEGATIVE", "NO_DOWNSTREAM_CHANGE")

result = {
    "pure_source_derived_ate": pure_ate,
    "stateful_block_order_naive_ate": drift_ate,
    "expected_true_treatment_effect_in_fixture": 2.0,
    "cases": {k: {"verdict": v[0], "reason": v[1]} for k, v in cases.items()},
    "assertions_passed": 8,
}
print(json.dumps(result, sort_keys=True, indent=2))
