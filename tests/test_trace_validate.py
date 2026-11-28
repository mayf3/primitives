from __future__ import annotations

import json
import unittest

from tools import trace_validate as validator


class CausalTraceTests(unittest.TestCase):
    def setUp(self):
        self.revisions = dict(zip(validator.REVISIONS, ('c' * 40, 'a' * 40, 'd' * 40,
                                                        validator.verifier_revision(), 'f' * 64)))
        coordinates = {
            'MODEL.ONE': ('MODEL', 'model_revision'),
            'TRANS.START': ('TRANSITION', 'model_revision'),
            'TRANS.FINISH': ('TRANSITION', 'model_revision'),
            'MAP.CORE': ('MAP', 'mapping_revision'),
            'CODE.CORE': ('CODE', 'code_revision'),
        }
        self.bindings, nodes = [], []
        for identifier, (kind, revision_field) in coordinates.items():
            coordinate = {'revision': self.revisions[revision_field], 'sha256': validator.sha256(identifier.encode())}
            self.bindings.append({'id': identifier, **coordinate})
            nodes.append({'id': identifier, 'kind': kind, 'coordinate_valid': True,
                          'resolved_coordinate': coordinate})
        links = [{'from': start, 'to': end, 'relation': relation} for start, end, relation in (
            ('MODEL.ONE', 'TRANS.START', 'defines'),
            ('MODEL.ONE', 'TRANS.FINISH', 'defines'),
            ('TRANS.START', 'MAP.CORE', 'implemented_by'),
            ('TRANS.FINISH', 'MAP.CORE', 'implemented_by'),
            ('MAP.CORE', 'CODE.CORE', 'points_to'),
        )]
        self.graph = {'schema_version': 'evidence-graph/v1', 'nodes': nodes, 'links': links}
        self.transitions = [
            {'transition_id': 'TRANS.START', 'from_observed': 'planned', 'event': 'start', 'to_observed': 'started'},
            {'transition_id': 'TRANS.FINISH', 'from_observed': 'started', 'event': 'finish', 'to_observed': 'done'},
        ]
        self.context = {'trace_id': 'causal-fixture', 'environment_profile': 'isolated'}
        self.contract = {
            'schema_version': validator.CONTRACT, **self.context, 'revisions': self.revisions,
            'bindings': self.bindings, 'transitions': self.transitions,
            'stutters': [{'mapping_id': 'MAP.CORE', 'event': 'admitted', 'states': ['planned'], 'initial_only': True}],
        }
        self.raw_rows = [b'{"kind":"first"}', b'{"kind":"second"}', b'{"kind":"third"}']

    def row(self, raw_line, action, **overrides):
        return {
            'schema_version': validator.SCHEMA, **self.context, **self.revisions,
            'event_id': f'event-{raw_line}', 'producer_id': 'alpha', 'producer_epoch': 0, 'seq': raw_line,
            'subject_id': 'visit-a', 'identity': {'attempt_id': 'attempt-a', 'generation': 1},
            'causal_parent_ids': [], 'segment_complete': True, **self.transitions[action],
            'raw_line': raw_line, 'payload_hash': validator.sha256(self.raw_rows[raw_line - 1]), **overrides,
        }

    @staticmethod
    def stream(producer_id, producer_epoch, last_seq):
        return {'producer_id': producer_id, 'producer_epoch': producer_epoch, 'first_seq': 1, 'last_seq': last_seq}

    def report(self, rows, streams, include_second_subject=False):
        source = b''.join(row + b'\n' for row in self.raw_rows[:len(rows)])
        normalized = b''.join((json.dumps(row) + '\n').encode() for row in rows)
        initial = {'visit-a': {'state': 'planned', 'identity': {'attempt_id': 'attempt-a', 'generation': 1}}}
        if include_second_subject:
            initial['visit-b'] = {'state': 'planned', 'identity': {'attempt_id': 'attempt-b', 'generation': 1}}
        manifest = {
            'schema_version': validator.SEGMENT, **self.context, 'revisions': self.revisions,
            'closed': True, 'collector_status': 'complete', 'streams': streams, 'initial': initial,
            'raw_sha256': validator.sha256(source), 'normalized_sha256': validator.sha256(normalized),
        }
        return validator.validate_trace(self.graph, self.contract, manifest, normalized, source)

    def assert_status(self, report, status, code=None):
        self.assertEqual(report['status'], status, report)
        if code:
            self.assertEqual(report['issues'][0]['code'], code)
        self.assertEqual(report['proof_status'], 'NOT_ESTABLISHED')
        self.assertEqual(report['acceptance_status'], 'NOT_ESTABLISHED')

    def test_same_subject_requires_cross_stream_causal_path(self):
        first = self.row(1, 0)
        last = self.row(2, 1, producer_id='beta', seq=1)
        streams = [self.stream('alpha', 0, 1), self.stream('beta', 0, 1)]
        self.assert_status(self.report([first, last], streams), 'UNKNOWN', 'SUBJECT_ORDER_UNPROVEN')
        last['causal_parent_ids'] = ['event-1']
        self.assert_status(self.report([last, first], streams), 'TRACE_CONFORMANT')

    def test_epoch_number_does_not_establish_order(self):
        first = self.row(1, 0)
        last = self.row(2, 1, producer_epoch=1, seq=1)
        streams = [self.stream('alpha', 0, 1), self.stream('alpha', 1, 1)]
        self.assert_status(self.report([first, last], streams), 'UNKNOWN', 'SUBJECT_ORDER_UNPROVEN')
        last['causal_parent_ids'] = ['event-1']
        self.assert_status(self.report([first, last], streams), 'TRACE_CONFORMANT')

    def test_partial_order_allows_independent_subjects_and_orders_reports_deterministically(self):
        rows = [self.row(1, 0), self.row(2, 0, producer_id='beta', seq=1, subject_id='visit-b',
                                        identity={'attempt_id': 'attempt-b', 'generation': 1})]
        streams = [self.stream('alpha', 0, 1), self.stream('beta', 0, 1)]
        forward = self.report(rows, streams, include_second_subject=True)
        backward = self.report(rows[::-1], streams[::-1], include_second_subject=True)
        self.assert_status(forward, 'TRACE_CONFORMANT')
        self.assert_status(backward, 'TRACE_CONFORMANT')
        self.assertEqual(forward['event_order'], backward['event_order'])

    def test_same_subject_order_may_be_transitive_through_other_subject(self):
        rows = [self.row(1, 0),
                self.row(2, 0, producer_id='beta', seq=1, subject_id='visit-b', causal_parent_ids=['event-1'],
                         identity={'attempt_id': 'attempt-b', 'generation': 1}),
                self.row(3, 1, producer_id='gamma', seq=1, causal_parent_ids=['event-2'])]
        streams = [self.stream(producer, 0, 1) for producer in ('alpha', 'beta', 'gamma')]
        report = self.report(rows, streams, include_second_subject=True)
        self.assert_status(report, 'TRACE_CONFORMANT')
        self.assertEqual(report['event_order'], ['event-1', 'event-2', 'event-3'])

    def test_causal_cycle_across_streams_is_rejected(self):
        rows = [self.row(1, 0, causal_parent_ids=['event-2']),
                self.row(2, 1, producer_id='beta', seq=1, causal_parent_ids=['event-1'])]
        streams = [self.stream('alpha', 0, 1), self.stream('beta', 0, 1)]
        self.assert_status(self.report(rows, streams), 'TRACE_DRIFTED', 'CAUSAL_CYCLE')

    def test_duplicate_normalized_events_and_raw_associations_are_rejected(self):
        first = self.row(1, 0)
        stream = [self.stream('alpha', 0, 2)]
        self.assert_status(self.report([first, self.row(2, 1, event_id='event-1')], stream),
                           'TRACE_INCOMPLETE', 'EVENT_ID_REUSED')
        duplicate_raw = {**self.row(2, 1), 'raw_line': 1, 'payload_hash': first['payload_hash']}
        self.assert_status(self.report([first, duplicate_raw], stream), 'TRACE_INCOMPLETE', 'RAW_ROW_REUSED')

    def test_consistent_old_verifier_label_does_not_match_running_checker(self):
        self.revisions['verifier_revision'] = 'e' * 64
        self.assert_status(self.report([self.row(1, 0)], [self.stream('alpha', 0, 1)]), 'STALE',
                           'RUNNING_VERIFIER_MISMATCH')

    def test_file_line_order_cannot_be_reassigned_as_a_contiguous_sequence(self):
        first = self.row(1, 0, seq=2, sequence_source='observed_raw_line')
        last = self.row(2, 1, seq=1, sequence_source='observed_raw_line')
        self.assert_status(self.report([first, last], [self.stream('alpha', 0, 2)]),
                           'TRACE_DRIFTED', 'RAW_LINE_SEQUENCE_MISMATCH')

    def test_initial_stutter_must_preserve_state_and_cannot_repeat(self):
        admission = {'transition_id': None, 'stutter_mapping_id': 'MAP.CORE', 'event': 'admitted',
                     'from_observed': 'planned', 'to_observed': 'planned'}
        first = self.row(1, 0, **admission)
        self.assert_status(self.report([first], [self.stream('alpha', 0, 1)]), 'TRACE_CONFORMANT')
        bogus = {**first, 'to_observed': 'started'}
        self.assert_status(self.report([bogus], [self.stream('alpha', 0, 1)]), 'TRACE_DRIFTED', 'STUTTER_NOT_ALLOWED')
        repeated = self.row(2, 0, **admission)
        self.assert_status(self.report([first, repeated], [self.stream('alpha', 0, 2)]),
                           'TRACE_DRIFTED', 'STUTTER_NOT_ALLOWED')


if __name__ == '__main__':
    unittest.main()
