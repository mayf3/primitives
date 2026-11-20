#!/usr/bin/env python3
"""Clean-build this proof slice and audit every declared theorem's axioms.

This checks the formal files, not their correspondence with a deployed system.
Only Lean's bundled libraries are used. No dependency download is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parent
VERSION = "4.19.0"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
PROOFS = [ROOT / "AgentWorkflow/Progress.lean", ROOT / "AgentWorkflow/Evidence.lean"]


def code_only(source: str) -> str:
    """Mask Lean comments (including nested blocks) and quoted strings.

    This is a small lexical guard for these files, not a Lean parser or proof
    checker. Kernel checking and the transitive axiom audit are authoritative.
    """
    out: list[str] = []
    i = 0
    depth = 0
    in_string = False
    while i < len(source):
        pair = source[i:i + 2]
        char = source[i]
        if depth:
            if pair == "/-":
                depth += 1
                out.extend("  ")
                i += 2
                continue
            if pair == "-/":
                depth -= 1
                out.extend("  ")
                i += 2
                continue
            out.append("\n" if char == "\n" else " ")
        elif in_string:
            if char == "\\":
                out.extend("  ")
                i += 2
                continue
            if char == '"':
                in_string = False
            out.append("\n" if char == "\n" else " ")
        elif pair == "/-":
            depth = 1
            out.extend("  ")
            i += 2
            continue
        elif pair == "--":
            end = source.find("\n", i)
            if end == -1:
                end = len(source)
            out.extend(" " * (end - i))
            i = end
            continue
        elif char == '"':
            in_string = True
            out.append(" ")
        else:
            out.append(char)
        i += 1
    if depth or in_string:
        raise ValueError("Unterminated block comment or string")
    return "".join(out)


def run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=120)
    if result.returncode:
        raise RuntimeError(f"{command!r} failed ({result.returncode}):\n{result.stdout}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", type=Path,
                        help="Directory containing the pinned lean and lake binaries")
    parser.add_argument("--output", type=Path, default=ROOT / "verification.json")
    args = parser.parse_args()
    env = os.environ.copy()
    if args.bin_dir:
        env["PATH"] = str(args.bin_dir.resolve()) + os.pathsep + env.get("PATH", "")
    for executable in ("lean", "lake"):
        if shutil.which(executable, path=env.get("PATH")) is None:
            raise RuntimeError(f"Missing {executable}; install the pinned toolchain first")
    version = run(["lean", "--version"], env).stdout.strip()
    short_version = run(["lean", "--short-version"], env).stdout.strip()
    if short_version != VERSION:
        raise RuntimeError(f"Expected Lean {VERSION}, got {short_version}")
    if (ROOT / "lean-toolchain").read_text().strip() != f"leanprover/lean4:v{VERSION}":
        raise RuntimeError("lean-toolchain disagrees with the verification pin")
    config = tomllib.loads((ROOT / "lakefile.toml").read_text())
    if config.get("require"):
        raise RuntimeError("This verification scope permits no external Lean packages")
    manifest = json.loads((ROOT / "lake-manifest.json").read_text())
    if manifest.get("packages") != []:
        raise RuntimeError("Expected an empty dependency manifest")

    input_paths = [ROOT / "lean-toolchain", ROOT / "lakefile.toml", ROOT / "lake-manifest.json",
                   ROOT / "AgentWorkflow.lean", ROOT / "AxiomAudit.lean",
                   ROOT / "verify.py", *PROOFS]

    def hashes() -> dict[str, str]:
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in input_paths}

    frozen_hashes = hashes()
    allowed_lean_files = {*PROOFS, ROOT / "AgentWorkflow.lean", ROOT / "AxiomAudit.lean"}
    actual_lean_files = {path for path in ROOT.rglob("*.lean")
                         if ".lake" not in path.relative_to(ROOT).parts}
    if actual_lean_files != allowed_lean_files:
        raise RuntimeError("Unexpected or missing Lean module; extend the audit scope explicitly")

    theorems: list[str] = []
    for path in sorted(ROOT.rglob("*.lean")):
        if ".lake" in path.relative_to(ROOT).parts:
            continue
        code = code_only(path.read_text())
        forbidden = re.search(r"\b(sorry|admit|axiom|native_decide)\b|debug\.skipKernelTC", code)
        if forbidden:
            raise RuntimeError(f"Forbidden proof escape in {path.name}: {forbidden[0]}")
        if path in PROOFS:
            namespaces = re.findall(r"^namespace\s+([\w.]+)\s*$", code, re.MULTILINE)
            if len(namespaces) != 1:
                raise RuntimeError(f"Expected one explicit namespace in {path.name}")
            names = re.findall(r"^theorem\s+([\w.]+)(?=\s|\{|\(|:)", code, re.MULTILINE)
            if not names:
                raise RuntimeError(f"No theorem declarations in {path.name}")
            if len(re.findall(r"\btheorem\b", code)) != len(names):
                raise RuntimeError(f"Unsupported theorem declaration style in {path.name}")
            theorems.extend(f"{namespaces[0]}.{name}" for name in names)
        elif re.search(r"\btheorem\b", code):
            raise RuntimeError(f"Theorems must be in an explicitly audited module: {path.name}")
    requested = re.findall(r"^#print axioms ([\w.]+)\s*$",
                           (ROOT / "AxiomAudit.lean").read_text(), re.MULTILINE)
    if len(set(theorems)) != len(theorems) or sorted(requested) != sorted(theorems):
        raise RuntimeError("AxiomAudit.lean must audit each declared theorem exactly once")

    commands = [
        ["lake", "clean"],
        ["lake", "build"],
        ["lake", "env", "lean", "-DwarningAsError=true", "AxiomAudit.lean"],
    ]
    records = []
    audit_output = ""
    for command in commands:
        result = run(command, env)
        records.append({"command": command, "exit_code": result.returncode})
        if command[-1] == "AxiomAudit.lean":
            audit_output = result.stdout
    pattern = r"'([^'\n]+)' (?:does not depend on any axioms|depends on axioms:\s*\[([^\]]*)\])"
    matched = re.findall(pattern, audit_output)
    axioms = {name: sorted(a.strip() for a in listed.split(",") if a.strip())
              for name, listed in matched}
    if len(matched) != len(theorems) or set(axioms) != set(theorems):
        raise RuntimeError(f"Incomplete/duplicate axiom output:\n{audit_output}")
    unexpected = {name: set(deps) - ALLOWED_AXIOMS for name, deps in axioms.items()
                  if set(deps) - ALLOWED_AXIOMS}
    if unexpected:
        raise RuntimeError(f"Unapproved transitive axioms: {unexpected}")
    if hashes() != frozen_hashes:
        raise RuntimeError("Proof/configuration/audit source changed during verification; rerun")
    final_lean_files = {path for path in ROOT.rglob("*.lean")
                        if ".lake" not in path.relative_to(ROOT).parts}
    if final_lean_files != allowed_lean_files:
        raise RuntimeError("Lean module set changed during verification; rerun")
    receipt = {
        "schema": "agent-workflow-lean-verification/v1",
        "status": "PASS_CONDITIONAL_FORMAL_SLICE",
        "lean_version": version,
        "dependencies": "Lean 4.19.0 bundled Init/Std only; no external packages",
        "commands": records,
        "source_sha256": frozen_hashes,
        "input_hashes_unchanged_during_verification": True,
        "theorems_audited": len(theorems),
        "allowed_standard_axioms": sorted(ALLOWED_AXIOMS),
        "theorem_axioms": dict(sorted(axioms.items())),
        "scope": {
            "conditional_model_theorems": True,
            "independent_kernel_implementation": False,
            "implementation_refinement": "NOT_PROVED",
            "production_verification": "NOT_PERFORMED",
            "probabilistic_retry_theorem": "NOT_FORMALIZED",
            "complete_later_model_migration": "NOT_COMPLETED",
        },
    }
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "theorems_audited": len(theorems),
                      "used_standard_axioms": sorted({a for ds in axioms.values() for a in ds}),
                      "receipt": args.output.name}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
