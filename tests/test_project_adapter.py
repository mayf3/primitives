from copy import deepcopy
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from project_adapter import REVISIONS, replay_adapter, run_adapter


WORKER = """
import json
import sys

role, behavior = sys.argv[1:]
count = 0
for line in sys.stdin:
    rpc = json.loads(line)
    method, params = rpc['method'], rpc['params']
    if method == 'reset':
        count = params['environment_profile']['start']
        result = None
    elif method == 'snapshot':
        result = {'count': count} if role == 'oracle' else {'native': count}
    elif method == 'abstract_state':
        result = {'count': params['snapshot']['native']}
    elif method == 'normalize':
        result = params['event']
    elif method == 'observe':
        result = params['result']['observation']
    elif method == 'execute':
        context = params['test_context']
        assert set(context) == {'index', 'seed'}
        command = params['command']['kind']
        mute = command == 'check'
        count += 1 if not mute or behavior == 'fake-stutter' else 0
        if behavior == 'state-drift':
            count += 1
        events = [] if mute or (behavior == 'drop' and role == 'sut') else [{'event': 'increment'}]
        result = {'state': {'count': count}, 'events': events, 'complete': behavior != 'partial',
                  'observation': 'UNKNOWN' if command == 'unknown' else 'PASS'}
        if mute:
            result['stutter'] = 'check-only'
    print(json.dumps({'id': rpc['id'], 'result': result}), flush=True)
if behavior == 'trailing':
    print('extra stdout', flush=True)
"""


class ProjectAdapterTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.script = Path(scratch.name).resolve() / "worker.py"
        self.script.write_text(WORKER, encoding="utf-8")

    def run_case(self, *, behavior="normal", oracle="normal", commands=("increment",), **overrides):
        configuration = {"sut_argv": [sys.executable, str(self.script), "sut", behavior],
                         "oracle_argv": [sys.executable, str(self.script), "oracle", oracle],
                         "seed": 917, "environment_profile": {"start": 0},
                         "commands": [{"kind": k} for k in commands], "mapping_id": "mapping",
                         "observation_id": "observation", "versions": {key: "a" * 40 for key in REVISIONS},
                         "stutters": {"check-only": "The query has no abstract write."}}
        return run_adapter(**(configuration | overrides))

    def test_both_workers_independent_and_every_step_replayable(self):
        report = self.run_case(commands=("increment", "check", "increment"))
        self.assertEqual(report["status"], "TRACE_CONFORMANT")
        self.assertEqual(report["initial"]["concrete"], {"native": 0})
        self.assertEqual([step["snapshot"]["abstract"]["count"] for step in report["steps"]], [1, 1, 2])
        self.assertNotEqual(report["workers"]["sut"]["pid"], report["workers"]["oracle"]["pid"])
        self.assertNotEqual(report["workers"]["sut"]["cwd"], report["workers"]["oracle"]["cwd"])
        sent = {}
        for role, transcript in report["workers"].items():
            frames = [json.loads(base64.b64decode(f["request_base64"])) for f in transcript["frames"]]
            sent[role] = [f["params"] for f in frames if f["method"] == "execute"]
        self.assertEqual(sent["sut"], sent["oracle"])
        replay = replay_adapter(report, report["input"]["versions"])
        self.assertEqual(replay["status"], "TRACE_CONFORMANT")
        self.assertEqual(replay["steps"], report["steps"])

    def test_observed_divergence_and_incomplete_capture_are_distinct(self):
        for behavior, expected in (("drop", "TRACE_DRIFTED"), ("state-drift", "TRACE_DRIFTED"),
                                   ("partial", "TRACE_INCOMPLETE"), ("trailing", "TRACE_INCOMPLETE")):
            with self.subTest(behavior=behavior):
                report = self.run_case(behavior=behavior)
                self.assertEqual(report["status"], expected)
                self.assertTrue(report["workers"]["sut"]["frames"])
                self.assertTrue(report["workers"]["oracle"]["frames"])

    def test_stutter_requires_justification_and_no_abstract_change(self):
        self.assertEqual(self.run_case(commands=("check",), stutters={})["status"], "UNKNOWN")
        result = self.run_case(commands=("check",), behavior="fake-stutter", oracle="fake-stutter")
        self.assertEqual(result["status"], "TRACE_DRIFTED")

    def test_unknown_observation_persists_through_unrelated_success(self):
        report = self.run_case(commands=("unknown", "check"))
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["unknown_steps"], [0])
        self.assertEqual(report["steps"][0]["transition_comparison"], "TRACE_CONFORMANT")
        self.assertEqual(report["steps"][1]["status"], "TRACE_CONFORMANT")
        self.assertEqual(self.run_case(behavior="trailing", commands=("unknown",))["status"], "TRACE_INCOMPLETE")

    def test_stale_versions_and_gates_fail_closed(self):
        fresh = {"probe": {"status": "PASS"}, "trace": {"status": "TRACE_CONFORMANT"}}
        report = self.run_case(evidence=fresh)
        self.assertEqual(report["status"], "TRACE_CONFORMANT")
        changed = report["input"]["versions"] | {"sut_revision": "b" * 40}
        self.assertEqual(replay_adapter(report, changed, fresh)["status"], "STALE")
        with self.assertRaisesRegex(ValueError, "independent evidence"):
            replay_adapter(report, report["input"]["versions"])
        tampered = deepcopy(report)
        tampered["input"]["commands"][0]["kind"] = "check"
        with self.assertRaisesRegex(ValueError, "recorded digest"):
            replay_adapter(tampered, report["input"]["versions"], fresh)
        for gates, expected in ((fresh | {"probe": {"status": "STALE"}}, "STALE"),
                                (fresh | {"trace": {}}, "TRACE_INCOMPLETE"),
                                (fresh | {"probe": {"status": "FAIL"}}, "UNKNOWN")):
            with self.subTest(expected=expected):
                checked = replay_adapter(report, report["input"]["versions"], gates)
                self.assertEqual(checked["status"], expected)
                self.assertEqual(checked["workers"], {})
