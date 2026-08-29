from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


workspace_path = Path("src/frankenstein2/gwt_workspace.py")
workspace = workspace_path.read_text(encoding="utf-8")
workspace = replace_once(
    workspace,
    "from dataclasses import dataclass\n",
    "from dataclasses import dataclass, field\n",
    label="dataclasses import",
)
workspace = replace_once(
    workspace,
    "_MAX_COST = 2**31 - 1\n",
    "_MAX_COST = 2**31 - 1\n_BROADCAST_FACTORY_SEAL = object()\n",
    label="factory seal constant",
)
workspace = replace_once(
    workspace,
    "    recipient_cell_ids: tuple[str, ...]\n    candidate_ids: tuple[str, ...]\n    candidate_payload_refs: tuple[str, ...]\n\n    schema = GWT_BROADCAST_SCHEMA\n",
    "    recipient_cell_ids: tuple[str, ...]\n    candidate_ids: tuple[str, ...]\n    candidate_payload_refs: tuple[str, ...]\n    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)\n\n    schema = GWT_BROADCAST_SCHEMA\n",
    label="BroadcastEnvelope seal field",
)
workspace = replace_once(
    workspace,
    "        object.__setattr__(self, \"candidate_ids\", candidate_ids)\n        object.__setattr__(self, \"candidate_payload_refs\", payload_refs)\n\n    def as_dict(self) -> dict[str, Any]:\n",
    "        object.__setattr__(self, \"candidate_ids\", candidate_ids)\n        object.__setattr__(self, \"candidate_payload_refs\", payload_refs)\n\n    def assert_builder_lineage(self) -> None:\n        if self._factory_seal is not _BROADCAST_FACTORY_SEAL:\n            raise GwtWorkspaceError(\"broadcast builder lineage is not verified\")\n\n    def as_dict(self) -> dict[str, Any]:\n",
    label="BroadcastEnvelope lineage validator",
)
workspace = replace_once(
    workspace,
    "        recipient_cell_ids=recipient_cell_ids,\n        candidate_ids=candidate_ids,\n        candidate_payload_refs=payload_refs,\n    )\n",
    "        recipient_cell_ids=recipient_cell_ids,\n        candidate_ids=candidate_ids,\n        candidate_payload_refs=payload_refs,\n        _factory_seal=_BROADCAST_FACTORY_SEAL,\n    )\n",
    label="create_broadcast seal injection",
)
workspace_path.write_text(workspace, encoding="utf-8")

uptake_path = Path("src/frankenstein2/gwt_uptake.py")
uptake = uptake_path.read_text(encoding="utf-8")
uptake = replace_once(
    uptake,
    "from frankenstein2.gwt_workspace import BroadcastEnvelope\n",
    "from frankenstein2.gwt_workspace import BroadcastEnvelope, GwtWorkspaceError\n",
    label="uptake workspace import",
)
uptake = replace_once(
    uptake,
    "    elif intervention.downstream_output_sha256 == control.downstream_output_sha256:\n        status = \"NO_CAUSAL_INFLUENCE_OBSERVED\"\n    else:\n        status = \"CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE\"\n",
    "    elif intervention.downstream_output_sha256 == control.downstream_output_sha256:\n        status = \"NO_CAUSAL_INFLUENCE_OBSERVED\"\n    else:\n        try:\n            broadcast.assert_builder_lineage()\n        except GwtWorkspaceError as exc:\n            raise GWTUptakeError(\"broadcast builder lineage is not verified\") from exc\n        status = \"CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE\"\n",
    label="positive causal lineage gate",
)
uptake_path.write_text(uptake, encoding="utf-8")

print("WP506 G5 candidate applied deterministically")
