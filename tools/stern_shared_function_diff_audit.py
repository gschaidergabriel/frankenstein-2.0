#!/usr/bin/env python3
"""P8 diff-audit tool: compares every top-level/nested function body shared
by name between ~/.claude/star/stern.py (the live-registered hook) and
~/frankenstein-repo/scripts/stern.py (the F2WP1207 research fork, common
ancestor commit 4f55d68, 2026-08-26). Read-only, makes no changes to either
file. Run it again any time drift between the two is suspected.

Result of the first run (2026-09-04, see
workpackages/evidence_inbox/F2-WP-1207/self_integration/
STERN_DIFF_AUDIT_20260904.md for the full writeup): 467/468 shared function
bodies byte-identical, 1 substantive diff (cmd_hook itself, exactly the two
known deliberate F2WP1207 call-site insertions), 0 unexplained drift.
"""
import ast
import hashlib
import sys
from pathlib import Path

FILE_A = Path.home() / ".claude" / "star" / "stern.py"
FILE_B = Path.home() / "frankenstein-repo" / "scripts" / "stern.py"


def extract_funcs(path):
    """Return dict: bare_name -> list of entries (usually 1; >1 means the
    name is reused at more than one nesting scope within the same file --
    not itself a cross-file risk, just noted). Walks the whole tree
    (module-level defs, defs inside classes, and defs nested inside other
    defs)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    lines = src.splitlines(keepends=True)
    funcs = {}
    dupes = {}

    def qualname(stack):
        return ".".join(stack) if stack else ""

    def visit(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
                seg = ast.get_source_segment(src, child)
                if seg is None:
                    seg = "".join(lines[child.lineno - 1: child.end_lineno])
                decorators = []
                for d in child.decorator_list:
                    try:
                        decorators.append(ast.unparse(d))
                    except Exception:
                        decorators.append("<decorator>")
                key_scope = qualname(stack)
                dupes[name] = dupes.get(name, 0) + 1
                entry = {
                    "source": seg,
                    "lineno": child.lineno,
                    "end_lineno": getattr(child, "end_lineno", None),
                    "is_async": isinstance(child, ast.AsyncFunctionDef),
                    "decorators": decorators,
                    "scope": key_scope,
                }
                funcs.setdefault(name, []).append(entry)
                visit(child, stack + [name])
            elif isinstance(child, ast.ClassDef):
                visit(child, stack + [child.name])
            else:
                visit(child, stack)

    visit(tree, [])
    return funcs, dupes


def normalize_ws(s):
    lines_out = []
    for line in s.splitlines():
        line = line.rstrip()
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        lines_out.append(stripped)
    return "\n".join(lines_out)


def main():
    funcs_a, dupes_a = extract_funcs(FILE_A)
    funcs_b, dupes_b = extract_funcs(FILE_B)

    names_a, names_b = set(funcs_a), set(funcs_b)
    shared = sorted(names_a & names_b)
    only_a, only_b = sorted(names_a - names_b), sorted(names_b - names_a)

    identical, ws_only, substantive = [], [], []
    for name in shared:
        src_a = funcs_a[name][0]["source"]
        src_b = funcs_b[name][0]["source"]
        if src_a == src_b:
            identical.append(name)
        elif normalize_ws(src_a) == normalize_ws(src_b):
            ws_only.append(name)
        else:
            substantive.append(name)

    print(f"shared={len(shared)} identical={len(identical)} "
          f"ws_only={len(ws_only)} substantive={len(substantive)} "
          f"only_a={len(only_a)} only_b={len(only_b)}")
    if substantive:
        print("SUBSTANTIVE DIFFS:", substantive)
    if only_a:
        print("ONLY IN star/stern.py:", only_a)
    if only_b:
        print("ONLY IN frankenstein-repo/stern.py:", only_b)


if __name__ == "__main__":
    main()
