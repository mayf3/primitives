#!/usr/bin/env python3
"""Offline, standard-library Evidence Graph Compiler. The graph is derived, never authoritative."""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "evidence-graph/v1"
RECEIPT = "evidence-receipt/v1"
KINDS = {"REQ","DEC","MODEL","STATE","TRANSITION","PROP","THM","LEAN","MAP","CODE","TEST","TRACE","ASSUMPTION","PROBE","ACCEPTANCE"}
SKIP = {".git",".hg",".svn",".venv","venv","node_modules","__pycache__",".mypy_cache",".pytest_cache",".lake","build","dist",".evidence-graph"}
NODE = re.compile(r"@evidence-node\s+(\{[^\n]*\})")
LINK = re.compile(r"@evidence-link\s+(\{[^\n]*\})")

def digest(data): return hashlib.sha256(data).hexdigest()
def now(): return datetime.now(timezone.utc)
def stamp(value):
    if not isinstance(value,str): return None
    try:
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except ValueError: return None

def project_revision(root):
    try:
        p=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],capture_output=True,text=True,timeout=2,check=True)
        s=p.stdout.strip()
        return s if re.fullmatch(r"[0-9a-f]{40}",s) else None
    except (OSError,subprocess.SubprocessError): return None

def files(root):
    for base,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in SKIP and not (Path(base)/d).is_symlink())
        for name in sorted(names):
            p=Path(base)/name
            if p.is_symlink() or p.suffix.lower() in {".png",".jpg",".jpeg",".gif",".webp",".pdf",".zip",".gz",".xz",".so",".a",".o",".class",".jar",".apk",".mp4",".mov",".wav",".mp3",".sqlite",".db"}: continue
            yield p

def safe_file(root, relative):
    if not isinstance(relative,str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("coordinate path must be project-relative")
    p=root/relative
    resolved=p.resolve(strict=True)
    resolved.relative_to(root.resolve())
    if p.is_symlink() or not resolved.is_file(): raise ValueError("coordinate must be a regular file inside project")
    return resolved

def load(root):
    nodes,links,errors=[],[],[]
    for p in files(root):
        try: raw=p.read_bytes(); text=raw.decode("utf-8")
        except (OSError,UnicodeDecodeError): continue
        src=p.relative_to(root).as_posix(); sha=digest(raw)
        for regex,target,kind in ((NODE,nodes,"node"),(LINK,links,"link")):
            for m in regex.finditer(text):
                try: obj=json.loads(m.group(1))
                except json.JSONDecodeError as e:
                    errors.append({"code":"MALFORMED_"+kind.upper(),"source":src,"detail":str(e)}); continue
                if kind=="node":
                    if not isinstance(obj,dict) or not isinstance(obj.get("id"),str) or not re.fullmatch(r"[A-Z][A-Z0-9_.:-]{1,127}",obj["id"]) or obj.get("kind") not in KINDS:
                        errors.append({"code":"INVALID_NODE","source":src,"detail":obj}); continue
                    target.append({**obj,"source":src,"source_sha256":sha})
                else:
                    if not isinstance(obj,dict) or not all(isinstance(obj.get(k),str) and obj[k] for k in ("from","to","relation")):
                        errors.append({"code":"INVALID_LINK","source":src,"detail":obj}); continue
                    target.append({**obj,"source":src})
        if p.suffix.lower()==".json":
            try: obj=json.loads(text)
            except json.JSONDecodeError: continue
            if isinstance(obj,dict) and obj.get("schema_version")==RECEIPT:
                if not isinstance(obj.get("nodes",[]),list) or not isinstance(obj.get("links",[]),list):
                    errors.append({"code":"INVALID_RECEIPT","source":src}); continue
                for n in obj.get("nodes",[]):
                    if isinstance(n,dict) and isinstance(n.get("id"),str) and n.get("kind") in KINDS:
                        nodes.append({**n,"source":src,"source_sha256":sha})
                    else: errors.append({"code":"INVALID_NODE","source":src,"detail":n})
                for e in obj.get("links",[]):
                    if isinstance(e,dict) and all(isinstance(e.get(k),str) and e[k] for k in ("from","to","relation")):
                        links.append({**e,"source":src})
                    else: errors.append({"code":"INVALID_LINK","source":src,"detail":e})
    return nodes,links,errors

def build(root):
    nodes,links,errors=load(root); first={}; duplicates=[]
    for n in nodes:
        if n["id"] in first: duplicates.append({"code":"DUPLICATE_ID","id":n["id"],"first_source":first[n["id"]],"duplicate_source":n["source"]})
        else: first[n["id"]]=n["source"]
    dangling=[{"code":"DANGLING_LINK",**e} for e in links if e["from"] not in first or e["to"] not in first]
    return {"schema_version":SCHEMA,"generated_at":now().isoformat(),"project_revision":project_revision(root),
            "nodes":sorted(nodes,key=lambda n:(n["id"],n["source"])),"links":sorted(links,key=lambda e:(e["from"],e["to"],e["relation"])),
            "diagnostics":errors+duplicates+dangling}

def reports(root,g):
    by={}; out={}
    for n in g["nodes"]: by.setdefault(n["id"],n)
    edges={}; incoming={}
    for e in g["links"]:
        edges.setdefault(e["from"],set()).add(e["to"])
        incoming.setdefault(e["to"],set()).add(e["from"])
    cov={"schema_version":SCHEMA,"requirements":[],"properties":[],"transitions":[],"mappings":[]}
    stale=[]
    for n in g["nodes"]:
        i,k=n["id"],n["kind"]; targets=edges.get(i,set())
        if k=="REQ" and n.get("critical"):
            ms=[x for x in targets if by.get(x,{}).get("kind")=="MODEL"]
            ac=[x for x in targets if by.get(x,{}).get("kind")=="ACCEPTANCE"]
            cov["requirements"].append({"id":i,"models":ms,"acceptances":ac,"covered":bool(ms and ac)})
        if k=="PROP" and n.get("critical"):
            ts=[x for x in targets if by.get(x,{}).get("kind")=="THM"]
            deferred=bool(n.get("deferred_reason"))
            cov["properties"].append({"id":i,"theorems":ts,"deferred":deferred,"covered":bool(ts) or deferred})
        if k in {"STATE","TRANSITION"} and n.get("critical"):
            maps=[x for x in targets if by.get(x,{}).get("kind")=="MAP"]
            cov["transitions"].append({"id":i,"mappings":maps,"covered":bool(maps)})
        if k=="MAP":
            issue=None; c=n.get("coordinate")
            if not isinstance(c,dict) or not isinstance(c.get("path"),str): issue="MAP requires coordinate.path"
            else:
                try:
                    p=safe_file(root,c["path"])
                    symbol=c.get("symbol")
                    if symbol:
                        try: src=p.read_text(encoding="utf-8")
                        except (OSError,UnicodeDecodeError): issue="MAP source is not UTF-8"
                        else:
                            if symbol not in src: issue="MAP symbol not found: "+str(symbol)
                except (OSError,ValueError) as e: issue="MAP path invalid: "+str(e)
            cov["mappings"].append({"id":i,"valid":issue is None,"issue":issue})
        if k in {"THM","TEST","TRACE"}:
            model_targets=[by[x] for x in targets if x in by and by[x]["kind"]=="MODEL"]
            expected=n.get("model_revision")
            if expected and model_targets:
                actual={m.get("revision") or m["source_sha256"] for m in model_targets}
                if expected not in actual: stale.append({"code":"MODEL_REVISION_MISMATCH","id":i,"expected":sorted(actual),"observed":expected})
            if k in {"TEST","TRACE"} and n.get("code_revision") and g["project_revision"] and n["code_revision"]!=g["project_revision"]:
                stale.append({"code":"CODE_REVISION_MISMATCH","id":i,"expected":g["project_revision"],"observed":n["code_revision"]})
        if k=="PROBE":
            executed=stamp(n.get("executed_at")); expires=stamp(n.get("expires_at")); ttl=n.get("ttl_seconds")
            expired=bool(expires and expires<=now())
            if executed and isinstance(ttl,(int,float)) and ttl>=0: expired |= executed.timestamp()+ttl<=now().timestamp()
            if expired: stale.append({"code":"PROBE_EXPIRED","id":i})
            if n.get("expected_environment_scope_hash") and n.get("environment_scope_hash")!=n["expected_environment_scope_hash"]:
                stale.append({"code":"PROBE_SCOPE_MISMATCH","id":i})
        if k=="ACCEPTANCE":
            # Accept either REQ -> ACCEPTANCE coverage links or
            # ACCEPTANCE -> REQ provenance links; both retain one authority.
            reqs=sorted({x for x in (targets | incoming.get(i,set())) if by.get(x,{}).get("kind")=="REQ"})
            if not reqs: stale.append({"code":"ACCEPTANCE_WITHOUT_REQUIREMENT","id":i})
            for req in reqs:
                rev=by[req].get("revision") or by[req]["source_sha256"]
                if n.get("spec_revision") and n["spec_revision"]!=rev:
                    stale.append({"code":"ACCEPTANCE_SPEC_REVISION_MISMATCH","id":i,"requirement":req,"expected":rev,"observed":n["spec_revision"]})
    summary={}
    for key in ("requirements","properties","transitions","mappings"):
        rows=cov[key]; flag="valid" if key=="mappings" else "covered"
        summary[key]={"total":len(rows),"covered":sum(bool(r[flag]) for r in rows),"uncovered":[r["id"] for r in rows if not r[flag]]}
    cov["summary"]=summary
    return {"coverage-report.json":cov,"dangling-links.json":{"schema_version":SCHEMA,"items":[d for d in g["diagnostics"] if d["code"]=="DANGLING_LINK"]},
            "stale-evidence.json":{"schema_version":SCHEMA,"items":stale}}

def atomic_write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def run(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command",choices=("build","validate","coverage","stale"))
    ap.add_argument("--project",default="."); ap.add_argument("--output",default=".evidence-graph")
    a=ap.parse_args(argv); root=Path(a.project).resolve()
    if not root.is_dir(): ap.error("project directory does not exist")
    g=build(root); r=reports(root,g); out=(root/a.output).resolve()
    try: out.relative_to(root)
    except ValueError: ap.error("output must remain inside project")
    atomic_write(out/"evidence-graph.json",g)
    for name,payload in r.items(): atomic_write(out/name,payload)
    if a.command=="build":
        print(json.dumps({"output":str(out),"nodes":len(g["nodes"]),"links":len(g["links"]),"diagnostics":len(g["diagnostics"])})); return 0
    if a.command=="coverage": print(json.dumps(r["coverage-report.json"],ensure_ascii=False,indent=2)); return 0
    if a.command=="stale":
        print(json.dumps(r["stale-evidence.json"],ensure_ascii=False,indent=2)); return 1 if r["stale-evidence.json"]["items"] else 0
    summary=r["coverage-report.json"]["summary"]
    uncovered=any(v["uncovered"] for v in summary.values())
    invalid=bool(g["diagnostics"] or uncovered or r["stale-evidence.json"]["items"])
    print(json.dumps({"diagnostics":g["diagnostics"],"coverage":summary,"stale":r["stale-evidence.json"]["items"],"output":str(out)},ensure_ascii=False,indent=2))
    return 1 if invalid else 0

if __name__=="__main__": raise SystemExit(run())
