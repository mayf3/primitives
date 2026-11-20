#!/usr/bin/env python3
"""Verify the domain Lean libraries and audit all explicit theorem declarations.

The restricted source convention below is an inventory guard, not a replacement
for Lean's kernel or a security sandbox. Correspondence with real programs,
natural-language meanings and human outcomes remains a separate obligation.
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

ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.19.0"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
INSTALL_OVERRIDES = {"LEAN_SYSROOT", "LEAN", "LAKE_HOME", "LAKE_OVERRIDE_LEAN",
                     "LEAN_GITHASH", "ELAN_TOOLCHAIN", "LEAN_PATH", "LEAN_SRC_PATH"}
IDENTIFIER = r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*"


def code_only(source: str) -> str:
    """Mask nested comments and strings while preserving newlines and offsets."""
    out: list[str] = []
    i, depth, quoted = 0, 0, False
    while i < len(source):
        pair, char = source[i:i + 2], source[i]
        if depth:
            if pair in ("/-", "-/"):
                depth += 1 if pair == "/-" else -1
                out.extend("  ")
                i += 2
                continue
            out.append("\n" if char == "\n" else " ")
        elif quoted:
            if char == "\\":
                out.extend("  ")
                i += 2
                continue
            if char == '"':
                quoted = False
            out.append("\n" if char == "\n" else " ")
        elif pair == "/-":
            depth = 1
            out.extend("  ")
            i += 2
            continue
        elif pair == "--":
            end = source.find("\n", i)
            end = len(source) if end < 0 else end
            out.extend(" " * (end - i))
            i = end
            continue
        elif char == '"':
            quoted = True
            out.append(" ")
        else:
            out.append(char)
        i += 1
    if depth or quoted:
        raise ValueError("Unterminated Lean comment or string")
    return "".join(out)


def local_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts or Path(relative).as_posix() != relative:
        raise ValueError(f"Expected a canonical repository-relative path: {relative}")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes repository: {relative}")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular repository file: {relative}")
    return path


def read_layout(root: Path = ROOT) -> tuple[dict, dict[str, list[str]], list[Path]]:
    """Validate ownership, imports and exhaustive source/axiom-audit inventory."""
    spec = json.loads((root / "lean-projects.json").read_text())
    if spec.get("schema") != "primitives-lean-projects/v1":
        raise ValueError("Unsupported Lean project manifest")
    expected_toolchain = f"leanprover/lean4:v{VERSION}"
    if spec.get("toolchain") != expected_toolchain:
        raise ValueError("Manifest toolchain differs from verifier pin")
    if (root / "lean-toolchain").read_text().strip() != expected_toolchain:
        raise ValueError("lean-toolchain differs from verifier pin")
    lake = tomllib.loads((root / "lakefile.toml").read_text())
    if set(lake) != {"name", "version", "defaultTargets", "leanOptions", "lean_lib"} or lake["name"] != "primitives":
        raise ValueError("Unexpected Lake configuration; review the build trust boundary")
    if lake.get("require") or lake.get("leanOptions") != {"warningAsError": True}:
        raise ValueError("Require bundled libraries only and warningAsError=true")
    lock = json.loads((root / "lake-manifest.json").read_text())
    if lock.get("packages") != []:
        raise ValueError("External Lean dependencies are outside this verification scope")
    projects = spec.get("projects", [])
    registry = json.loads((root / "registry.json").read_text())
    expected_domains = {"meta", *(module["id"] for module in registry["modules"])}
    domains = [project["domain"] for project in projects]
    libraries = [project["library"] for project in projects]
    if len(domains) != len(set(domains)) or set(domains) != expected_domains:
        raise ValueError("Register exactly one Lean project for meta and each domain")
    if len(libraries) != len(set(libraries)):
        raise ValueError("Duplicate Lean library name")
    if set(lake.get("defaultTargets", [])) != set(libraries):
        raise ValueError("Lake defaultTargets must include every library")
    expected_libraries = [{"name": p["library"], "srcDir": p["directory"]} for p in projects]
    if lake.get("lean_lib") != expected_libraries:
        raise ValueError("Lake libraries and ownership manifest disagree")

    all_files: set[Path] = set()
    all_adapters: set[Path] = set()
    theorem_names: dict[str, list[str]] = {}
    inputs = [local_path(root, name) for name in
              ("lean-projects.json", "lean-toolchain", "lakefile.toml", "lake-manifest.json",
               "registry.json", "tools/verify_lean.py")]
    core = next(p for p in projects if p["domain"] == "meta")
    core_modules = set(core["modules"])
    for project in projects:
        domain, library, directory = project["domain"], project["library"], project["directory"]
        expected_dir = "meta/lean" if domain == "meta" else f"domains/{domain}/lean"
        if directory != expected_dir:
            raise ValueError(f"Nonstandard proof directory: {domain}")
        modules = project["modules"]
        if len(modules) != len(set(modules)) or library not in modules:
            raise ValueError(f"Duplicate modules or missing library entry: {domain}")
        allowed_imports = set(modules) | (core_modules if domain != "meta" else set())
        names: list[str] = []
        for module in modules:
            if not re.fullmatch(IDENTIFIER, module) or not (module == library or module.startswith(library + ".")):
                raise ValueError(f"Module escapes its library: {module}")
            relative = directory + "/" + module.replace(".", "/") + ".lean"
            path = local_path(root, relative)
            all_files.add(path)
            inputs.append(path)
            code = code_only(path.read_text())
            forbidden = re.search(
                r"\b(sorry|admit|axiom|native_decide|unsafe|partial|run_elab|initialize|"
                r"builtin_initialize|elab|macro|syntax|set_option|attribute)\b|#|@\[|\bby\s+native\b",
                code, re.MULTILINE)
            if forbidden:
                raise ValueError(f"Unreviewed proof escape/metaprogram in {relative}: {forbidden[0]}")
            imports = re.findall(r"^import\s+([^\n]+)$", code, re.MULTILINE)
            if len(re.findall(r"\bimport\b", code)) != len(imports):
                raise ValueError(f"Unsupported import syntax in {relative}")
            for line in imports:
                for imported in line.split():
                    if imported not in allowed_imports and imported != "Std" and imported != "Init" and not imported.startswith(("Std.", "Init.")):
                        raise ValueError(f"Unregistered or cross-domain import in {relative}: {imported}")
            declarations = re.findall(rf"^theorem\s+({IDENTIFIER})(?=\s|\{{|\(|:)", code, re.MULTILINE)
            if len(re.findall(r"\btheorem\b", code)) != len(declarations):
                raise ValueError(f"Unsupported theorem declaration style in {relative}")
            if declarations:
                namespaces = re.findall(rf"^namespace\s+({IDENTIFIER})\s*$", code, re.MULTILINE)
                if len(namespaces) != 1 or not (namespaces[0] == library or namespaces[0].startswith(library + ".")):
                    raise ValueError(f"Use one library-owned namespace in {relative}")
                names.extend(f"{namespaces[0]}.{name}" for name in declarations)
            elif module != library:
                raise ValueError(f"Proof module has no audited theorem: {relative}")
        if not names or len(names) != len(set(names)):
            raise ValueError(f"Empty/duplicate theorem inventory in {domain}")
        theorem_names[domain] = names
        for check in project.get("checks", []):
            if not check["script"].startswith(directory + "/"):
                raise ValueError(f"Domain adapter is outside its proof directory: {domain}")
            adapter = local_path(root, check["script"])
            if not adapter.resolve().is_relative_to((root / directory).resolve()) or adapter.suffix != ".py":
                raise ValueError(f"Invalid domain adapter: {domain}")
            if adapter in all_adapters or not check.get("inputs"):
                raise ValueError(f"Duplicate adapter or missing bound input: {domain}")
            all_adapters.add(adapter)
            inputs.append(adapter)
            for relative in check["inputs"]:
                if not relative.startswith(f"domains/{domain}/"):
                    raise ValueError(f"Domain adapter reads another domain: {relative}")
                path = local_path(root, relative)
                if not path.resolve().is_relative_to((root / f"domains/{domain}").resolve()):
                    raise ValueError(f"Domain adapter reads another domain: {relative}")
                inputs.append(path)
    def is_working_source(path: Path) -> bool:
        parts = path.relative_to(root).parts
        if parts[0] in (".git", ".lake"):
            return False
        return not (len(parts) >= 3 and parts[0] == "domains" and parts[2] == "sources")

    actual_files = {p for p in root.rglob("*.lean") if is_working_source(p)}
    if actual_files != all_files:
        extra = sorted(str(p.relative_to(root)) for p in actual_files - all_files)
        missing = sorted(str(p.relative_to(root)) for p in all_files - actual_files)
        raise ValueError(f"Lean source inventory mismatch; extra={extra}, missing={missing}")
    actual_adapters = {p for project in projects for p in (root / project["directory"]).rglob("*.py")}
    if actual_adapters != all_adapters:
        raise ValueError("Lean adapter inventory mismatch; each adapter needs explicit bound inputs")
    for directory in [root / "meta/lean", *(root / f"domains/{d}/lean" for d in domains if d != "meta")]:
        for name in ("lakefile.toml", "lakefile.lean", "lean-toolchain", "verify.py", "AxiomAudit.lean"):
            if (directory / name).exists():
                raise ValueError(f"Duplicate build/audit configuration: {directory / name}")
    return spec, theorem_names, sorted(set(inputs))


def source_hashes(paths: list[Path], root: Path = ROOT) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def parse_axioms(output: str, expected: list[str]) -> dict[str, list[str]]:
    pattern = r"'([^'\n]+)' (?:does not depend on any axioms|depends on axioms:\s*\[([^\]]*)\])"
    matches = re.findall(pattern, output)
    axioms = {name: sorted(a.strip() for a in listed.split(",") if a.strip()) for name, listed in matches}
    if len(matches) != len(expected) or set(axioms) != set(expected):
        raise ValueError("Incomplete, duplicate or unexpected axiom audit output")
    bad = {name: sorted(set(deps) - ALLOWED_AXIOMS) for name, deps in axioms.items()
           if set(deps) - ALLOWED_AXIOMS}
    if bad:
        raise ValueError(f"Unapproved transitive axioms: {bad}")
    return dict(sorted(axioms.items()))


def execute(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=180)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command!r}\n{result.stdout}")
    return result


def report_path(domain: str | None, requested: Path | None, root: Path = ROOT) -> Path:
    output = requested or (root / ".lake/verification" / f"{domain}.json" if domain else root / "lean-verification.json")
    if domain and output.resolve() == (root / "lean-verification.json").resolve():
        raise ValueError("A partial domain run cannot overwrite the full verification receipt")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", type=Path, help="Directory containing pinned lean and lake")
    parser.add_argument("--domain", help="Verify one domain (including meta), plus its generic core")
    parser.add_argument("--output", type=Path, help="Optional report path; cannot overwrite source inputs")
    parser.add_argument("--check-layout", action="store_true", help="Validate inventory without claiming proofs checked")
    args = parser.parse_args()
    spec, inventory, paths = read_layout()
    if args.domain and args.domain not in inventory:
        raise ValueError(f"Unknown domain: {args.domain}")
    if args.check_layout:
        print(json.dumps({"status": "PASS_LAYOUT_ONLY", "theorems_declared": sum(map(len, inventory.values())),
                          "kernel_checked": False}, ensure_ascii=False))
        return 0
    selected = [p for p in spec["projects"] if not args.domain or p["domain"] in ("meta", args.domain)]
    env = {key: value for key, value in os.environ.items() if key not in INSTALL_OVERRIDES}
    if args.bin_dir:
        env["PATH"] = str(args.bin_dir.resolve()) + os.pathsep + env.get("PATH", "")
    for name in ("lean", "lake"):
        if not shutil.which(name, path=env.get("PATH")):
            raise RuntimeError(f"Missing {name}; install {spec['toolchain']}")
    if execute(["lean", "--short-version"], env).stdout.strip() != VERSION:
        raise RuntimeError(f"Expected exactly Lean {VERSION}")
    version = execute(["lean", "--version"], env).stdout.strip()
    hashes = source_hashes(paths)
    output = report_path(args.domain, args.output)
    if output.resolve() in {path.resolve() for path in paths}:
        raise ValueError("Report path would overwrite a verification input")
    commands = []
    command = ["lake", "clean"]
    execute(command, env)
    commands.append({"command": command, "exit_code": 0})
    command = ["lake", "build", *(p["library"] for p in selected)]
    execute(command, env)
    commands.append({"command": command, "exit_code": 0})
    temp = ROOT / ".lake/verification"
    temp.mkdir(parents=True, exist_ok=True)
    audit = temp / "AxiomAudit.lean"
    names = [name for p in selected for name in inventory[p["domain"]]]
    audit.write_text("\n".join([*(f"import {p['library']}" for p in selected),
                               *(f"#print axioms {name}" for name in names)]) + "\n")
    audit_hash = hashlib.sha256(audit.read_bytes()).hexdigest()
    command = ["lake", "env", "lean", "-DwarningAsError=true", str(audit.relative_to(ROOT))]
    axioms = parse_axioms(execute(command, env).stdout, names)
    if hashlib.sha256(audit.read_bytes()).hexdigest() != audit_hash:
        raise RuntimeError("Generated axiom audit changed during verification")
    commands.append({"command": command, "exit_code": 0})
    for project in selected:
        for check in project.get("checks", []):
            command = [sys.executable, check["script"], "--lake", "lake"]
            execute(command, env)
            commands.append({"command": ["python3", *command[1:]], "exit_code": 0})
    final_spec, final_inventory, final_paths = read_layout()
    if final_spec != spec or final_inventory != inventory or source_hashes(final_paths) != hashes:
        raise RuntimeError("Verification inputs changed during the run; rerun against stable sources")
    report = {
        "schema": "primitives-lean-verification/v1",
        "status": "PASS_CONDITIONAL_MODEL_PROOFS",
        "selection": args.domain or "all",
        "lean_version": version,
        "dependencies": "Pinned Lean Init/Std only; no external packages",
        "source_sha256": hashes,
        "input_hashes_match_before_after": True,
        "generated_axiom_audit_sha256": audit_hash,
        "commands": commands,
        "theorems_audited": len(names),
        "domains": {p["domain"]: {"library": p["library"], "directory": p["directory"],
                    "theorems_audited": len(inventory[p["domain"]])} for p in selected},
        "theorem_axioms": axioms,
        "scope": {"conditional_model_theorems": True, "independent_kernel_implementation": False,
                  "production_implementation_refinement": "NOT_PROVED",
                  "empirical_user_or_learning_effect": "NOT_TESTED",
                  "primitive_global_minimality": "NOT_PROVED"},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(output)
    print(json.dumps({"status": report["status"], "selection": report["selection"],
                      "theorems_audited": len(names), "domains": report["domains"],
                      "receipt": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
