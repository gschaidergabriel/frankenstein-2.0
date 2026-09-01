# GRID10 — first isolated laboratory prototype

`labs/grid10` is the first Frankenstein 2.0 laboratory prototype for the GRID10 fabric family. It is deliberately **not** wired into canonical EntityOS/F2 state, Voice/FDX, effects, GWT/J-Space or training.

## What this prototype measures

The bounded discriminator uses only the Python standard library and an isolated caller-selected SQLite database in WAL mode. The acceptance suite checks:

- ten independent OS processes join the same WAL fabric;
- task claims use exact-epoch CAS and stale epochs fail closed;
- ordinary workers emit to a result channel rather than directly creating committed state;
- a single scope/generation/token-bound coordinator lease commits pending results;
- a wrong coordinator token fails closed;
- a real OS `SIGKILL` of a task claimant is followed by stale-claim recovery, an independent replacement worker, commit and persisted readback naming the replacement as source;
- restart generation invalidates pre-restart coordinator authority.

Run locally:

```bash
cd labs/grid10
python3 -m unittest -v
```

## Provenance

The architectural lineage is bound to `gschaidergabriel/clay-global-research-entity` rather than inferred from prose:

- refreshed Clay head: `8d8d7616aab21e0aceb46862f04df51db8d5f2dd`;
- observed `tools/grid10_fabric.py` history commit: `a08ce8addabd365ef55394fd4d4af811cac59648`;
- observed latest `tools/grid10_node.py` path commit during admission: `be63cb6880bb0b90b707f0f4cc3970de6c2903d2`;
- independent replacement-process SIGKILL acceptance addition: `6ed5646ed01b8ca99947d8e3ca6325ad9b8cb4c1`.

The user also supplied `GRID10_Fabric_2026-08-27.zip`. Its bytes were not readable in this execution environment, so this admission **does not claim a ZIP hash, byte-equivalence, or verbatim import**. This prototype is a reduced independently implemented F2 lab boundary informed by repository-verifiable GRID10 lineage.

## Evidence law

Local sandbox success or repository CI success may close only this repository/laboratory component boundary. It does **not** mint:

- owner-VPS GRID10 runtime credit;
- physical GRID10 credit;
- GWT/J-Space causal credit;
- effect/completion credit;
- training credit;
- whole-product acceptance.

The next legal promotion after repository CI is one exact owner-VPS subject/run for this already-frozen lab discriminator, followed by receipt, state event and reconciliation. No second GRID10 architecture is required.
