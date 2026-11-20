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
COMPILED_AUDIT_PREFIX = "PRIMITIVES_COMPILED_AUDIT "


def code_only(source: str) -> str:
    """Mask literal payloads/comments, never code between character literals.

    This is a restricted source-style check, not a complete Lean parser. Lean
    4.19's identifier and character rules are in Init/Meta.lean and
    Lean/Parser/Basic.lean. Raw strings are rejected rather than approximated.
    The independent compiled-environment audit below is the coverage backstop.
    """
    out = list(source)

    def mask(start: int, stop: int) -> None:
        out[start:stop] = ["\n" if c == "\n" else " " for c in source[start:stop]]

    def letter_like(c: str) -> bool:
        n = ord(c)
        return ((0x3B1 <= n <= 0x3C9 and n != 0x3BB)
                or (0x391 <= n <= 0x3A9 and n not in (0x3A0, 0x3A3))
                or any(a <= n <= b for a, b in
                       ((0x3CA, 0x3FB), (0x1F00, 0x1FFE),
                        (0x2100, 0x214F), (0x1D49C, 0x1D59F))))

    def id_first(c: str) -> bool:
        return c == "_" or "a" <= c <= "z" or "A" <= c <= "Z" or letter_like(c)

    def id_rest(c: str) -> bool:
        n = ord(c)
        return (id_first(c) or "0" <= c <= "9" or c in "'!?"
                or any(a <= n <= b for a, b in
                       ((0x2080, 0x2089), (0x2090, 0x209C), (0x1D62, 0x1D6A)))
                or n == 0x2C7C)

    def escaped_end(start: int, in_string: bool) -> int:
        if start + 1 >= len(source):
            raise ValueError("Unterminated Lean literal escape")
        escaped = source[start + 1]
        if escaped in "\\\"'rnt" or (in_string and escaped == "\n"):
            return start + 2
        digits = {"x": 2, "u": 4}.get(escaped)
        if digits and re.fullmatch(r"[0-9A-Fa-f]{%d}" % digits,
                                   source[start + 2:start + 2 + digits]):
            return start + 2 + digits
        raise ValueError("Unsupported Lean literal escape")

    i = 0
    while i < len(source):
        pair, char = source[i:i + 2], source[i]
        if pair == "/-":
            start, depth = i, 1
            i += 2
            while i < len(source) and depth:
                pair = source[i:i + 2]
                if pair in ("/-", "-/"):
                    depth += 1 if pair == "/-" else -1
                    i += 2
                else:
                    i += 1
            if depth:
                raise ValueError("Unterminated Lean comment")
            mask(start, i)
        elif pair == "--":
            end = source.find("\n", i)
            end = len(source) if end < 0 else end
            mask(i, end)
            i = end
        elif char == "«":
            end = source.find("»", i + 1)
            if end < 0:
                raise ValueError("Unterminated Lean identifier escape")
            # Keep delimiters so a quoted import/declaration cannot disappear.
            mask(i + 1, end)
            i = end + 1
        elif char == "r" and re.match(r'r#*"', source[i:]):
            raise ValueError("Raw Lean strings are outside the restricted source style")
        elif id_first(char):
            # In x', x'' and α', apostrophes are part of the identifier.
            i += 1
            while i < len(source) and id_rest(source[i]):
                i += 1
        elif char == "'":
            start = i
            i += 1
            if i >= len(source):
                raise ValueError("Unterminated Lean character literal")
            i = escaped_end(i, False) if source[i] == "\\" else i + 1
            if i >= len(source) or source[i] != "'":
                raise ValueError("Unsupported Lean character literal")
            i += 1
            mask(start, i)
        elif char == '"':
            start = i
            i += 1
            while i < len(source) and source[i] != '"':
                i = escaped_end(i, True) if source[i] == "\\" else i + 1
            if i >= len(source):
                raise ValueError("Unterminated Lean string")
            i += 1
            mask(start, i)
        else:
            i += 1
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


def audit_source(projects: list[dict], names: list[str]) -> str:
    """Audit declarations from the loaded kernel environment, not just regexes.

    The generated module is trusted verifier code. Repository proof modules
    cannot import Lean or run this metaprogramming themselves. Module ownership
    includes private declarations and compiler-generated logical helpers.
    Lean also exports unsafe code-generation helpers; its safety metadata
    distinguishes those from logic, without guessing from their names.
    """
    modules = [module for project in projects for module in project["modules"]]
    header = ["import Lean", *(f"import {p['library']}" for p in projects),
              *(f"#print axioms {name}" for name in names)]
    compiled = '''
open Lean in
run_elab do
  let env ← getEnv
  let modules : List String := MODULE_LIST
  let present := modules.filter fun module =>
    env.header.moduleNames.any fun name => name.toString == module
  let mut declarations : Array Json := #[]
  let mut unsafeNames : Array Json := #[]
  let mut partialNames : Array Json := #[]
  for (name, info) in env.constants do
    if let some index := env.getModuleIdxFor? name then
      let owner := env.header.moduleNames[index]!
      if modules.contains owner.toString then
        if info.isUnsafe || info.isPartial then
          if info.isTheorem then
            throwError "Cannot exclude a theorem from the compiled audit: {name}"
          if info.isUnsafe then
            unsafeNames := unsafeNames.push (Json.str name.toString)
          else
            partialNames := partialNames.push (Json.str name.toString)
          continue
        let kind := match info with
          | .axiomInfo _ => "axiom"
          | .thmInfo _ => "theorem"
          | .defnInfo _ => "definition"
          | .opaqueInfo _ => "opaque"
          | .quotInfo _ => "quotient"
          | .inductInfo _ => "inductive"
          | .ctorInfo _ => "constructor"
          | .recInfo _ => "recursor"
        let axioms ← collectAxioms name
        declarations := declarations.push (Json.mkObj [
          ("name", Json.str name.toString),
          ("module", Json.str owner.toString),
          ("kind", Json.str kind),
          ("axioms", Json.arr (axioms.map fun axiomName => Json.str axiomName.toString))])
  IO.println ("AUDIT_PREFIX" ++ (Json.mkObj [
    ("schema", Json.str "primitives-compiled-audit/v1"),
    ("modules", Json.arr (present.toArray.map Json.str)),
    ("excluded_unsafe", Json.arr unsafeNames),
    ("excluded_partial", Json.arr partialNames),
    ("declarations", Json.arr declarations)]).compress)
'''
    return "\n".join(header) + "\n" + compiled.replace(
        "MODULE_LIST", json.dumps(modules)).replace("AUDIT_PREFIX", COMPILED_AUDIT_PREFIX)


def parse_compiled_audit(output: str, projects: list[dict],
                         expected: list[str]) -> tuple[dict[str, dict], list[str], list[str]]:
    lines = [line[len(COMPILED_AUDIT_PREFIX):] for line in output.splitlines()
             if line.startswith(COMPILED_AUDIT_PREFIX)]
    if len(lines) != 1:
        raise ValueError("Missing or duplicate compiled-environment audit")
    payload = json.loads(lines[0])
    modules = {module for project in projects for module in project["modules"]}
    if (not isinstance(payload, dict)
            or payload.get("schema") != "primitives-compiled-audit/v1"
            or not isinstance(payload.get("modules"), list)
            or any(not isinstance(module, str) for module in payload["modules"])
            or len(payload["modules"]) != len(modules)
            or set(payload["modules"]) != modules
            or not isinstance(payload.get("declarations"), list)):
        raise ValueError("Incomplete compiled module inventory")
    kinds = {"axiom", "theorem", "definition", "opaque", "quotient", "inductive",
             "constructor", "recursor"}
    declarations = {}
    for record in payload["declarations"]:
        if (not isinstance(record, dict) or set(record) != {"name", "module", "kind", "axioms"}
                or not isinstance(record["name"], str) or not record["name"]
                or record["name"] in declarations or not isinstance(record["module"], str)
                or record["module"] not in modules or not isinstance(record["kind"], str)
                or record["kind"] not in kinds or not isinstance(record["axioms"], list)
                or any(not isinstance(axiom, str) for axiom in record["axioms"])):
            raise ValueError("Malformed or duplicate compiled declaration")
        if record["kind"] == "axiom":
            raise ValueError(f"Repository-defined compiled axiom: {record['name']}")
        bad = sorted(set(record["axioms"]) - ALLOWED_AXIOMS)
        if bad:
            raise ValueError(f"Unapproved compiled transitive axioms: {record['name']}: {bad}")
        declarations[record["name"]] = {"module": record["module"], "kind": record["kind"],
                                         "axioms": sorted(set(record["axioms"]))}
    missing = [name for name in expected if declarations.get(name, {}).get("kind") != "theorem"]
    if missing:
        raise ValueError(f"Explicit theorems missing from compiled environment: {missing}")
    exclusions = []
    seen = set(declarations)
    for category in ("unsafe", "partial"):
        excluded = payload.get(f"excluded_{category}")
        if (not isinstance(excluded, list) or any(not isinstance(name, str) for name in excluded)
                or len(set(excluded)) != len(excluded) or set(excluded) & seen):
            raise ValueError(f"Malformed {category} compiler-declaration inventory")
        exclusions.append(sorted(excluded))
        seen.update(excluded)
    return dict(sorted(declarations.items())), *exclusions


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
    audit.write_text(audit_source(selected, names))
    audit_hash = hashlib.sha256(audit.read_bytes()).hexdigest()
    command = ["lake", "env", "lean", "-DwarningAsError=true", str(audit.relative_to(ROOT))]
    audit_output = execute(command, env).stdout
    axioms = parse_axioms(audit_output, names)
    compiled, excluded_unsafe, excluded_partial = parse_compiled_audit(audit_output, selected, names)
    if any(compiled[name]["axioms"] != deps for name, deps in axioms.items()):
        raise RuntimeError("Source-name and compiled-environment axiom audits disagree")
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
        "dependencies": "Pinned Lean distribution: Init/Std model dependencies and Lean audit tooling; no external packages",
        "source_sha256": hashes,
        "input_hashes_match_before_after": True,
        "generated_axiom_audit_sha256": audit_hash,
        "commands": commands,
        "theorems_audited": len(names),
        "compiled_declarations_audited": len(compiled),
        "compiled_theorems_audited": sum(d["kind"] == "theorem" for d in compiled.values()),
        "compiled_audit_scope": "Every safe logical declaration in the registered modules",
        "unsafe_compiler_declarations_excluded": excluded_unsafe,
        "partial_compiler_declarations_excluded": excluded_partial,
        "domains": {p["domain"]: {"library": p["library"], "directory": p["directory"],
                    "theorems_audited": len(inventory[p["domain"]])} for p in selected},
        "theorem_axioms": axioms,
        "compiled_declarations": compiled,
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
                      "compiled_declarations_audited": report["compiled_declarations_audited"],
                      "compiled_theorems_audited": report["compiled_theorems_audited"],
                      "receipt": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
