#!/usr/bin/env python3
"""Validate a sealed finite model trace against an Evidence Graph and a contract."""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


SCHEMA = 'model-trace/v1'
CONTRACT = 'model-trace-contract/v1'
SEGMENT = 'model-trace-segment/v1'
REPORT = 'model-trace-report/v1'
REVISIONS = ('code_revision', 'model_revision', 'mapping_revision',
             'verifier_revision', 'normalizer_revision')
SHA256 = re.compile(r'[a-f0-9]{64}\Z')
SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'schemas/model-trace-v1.schema.json'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verifier_revision(schema_bytes=None):
    schema = SCHEMA_PATH.read_bytes() if schema_bytes is None else schema_bytes
    fingerprints = sha256(Path(__file__).read_bytes()) + sha256(schema)
    return sha256(fingerprints.encode('ascii'))


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def is_digest(value):
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def identity_valid(value):
    return isinstance(value, dict) and bool(value) and all(
        nonempty(key) and (nonempty(v) or integer(v)) for key, v in value.items()
    )


def revisions_valid(value):
    return isinstance(value, dict) and set(value) == set(REVISIONS) and all(
        nonempty(value[key]) for key in REVISIONS
    )


def unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError(f'duplicate JSON key: {key}')
        fields[key] = value
    return fields


def reject_constant(token):
    raise ValueError(f'invalid JSON constant: {token}')


def load_json(data):
    return json.loads(data.decode('utf-8'), object_pairs_hook=unique_fields,
                      parse_constant=reject_constant)


def jsonl_lines(data):
    return data.removesuffix(b'\n').split(b'\n') if data else []


def event_schema_valid(row, schema):
    if not isinstance(row, dict) or not schema['required_set'] <= row.keys() <= schema['field_names']:
        return False
    if row['schema_version'] != SCHEMA or type(row['segment_complete']) is not bool:
        return False
    for key in schema['required_text']:
        if not nonempty(row.get(key)):
            return False
    for key in schema['nullable_text']:
        if row[key] is not None and not nonempty(row[key]):
            return False
    for key in schema['optional_text']:
        if key in row and not nonempty(row[key]):
            return False
    parents = row['causal_parent_ids']
    return (isinstance(parents, list) and all(nonempty(p) for p in parents)
            and len(set(parents)) == len(parents) and identity_valid(row['identity'])
            and integer(row['producer_epoch']) and integer(row['seq'], 1)
            and integer(row['raw_line'], 1) and is_digest(row['payload_hash'])
            and not (row['transition_id'] is not None and 'stutter_mapping_id' in row))


def read_schema(schema_bytes):
    schema = load_json(schema_bytes)
    properties = schema['properties']
    return {
        'required_set': set(schema['required']),
        'field_names': set(properties),
        'required_text': {key for key in schema['required'] if properties[key].get('type') == 'string'},
        'optional_text': {key for key in properties if key not in schema['required']},
        'nullable_text': {key for key, field in properties.items() if field.get('type') == ['string', 'null']},
    }


def issue(code, **details):
    return {'code': code, **details}


def contract_parts(contract):
    if (not isinstance(contract, dict) or contract.get('schema_version') != CONTRACT
            or not nonempty(contract.get('trace_id')) or not nonempty(contract.get('environment_profile'))
            or not revisions_valid(contract.get('revisions'))):
        return None
    bindings, rules, stutters = (contract.get('bindings'), contract.get('transitions'),
                                 contract.get('stutters', []))
    if not isinstance(bindings, list) or not bindings or not isinstance(rules, list) or not rules:
        return None
    if not isinstance(stutters, list):
        return None
    if any(not isinstance(b, dict) or not nonempty(b.get('id')) or not nonempty(b.get('revision'))
           or not is_digest(b.get('sha256')) for b in bindings):
        return None
    if any(not isinstance(r, dict) or r.keys() != {'transition_id', 'from_observed', 'event', 'to_observed'}
           or not all(nonempty(v) for v in r.values()) for r in rules):
        return None
    for s in stutters:
        if (not isinstance(s, dict) or not nonempty(s.get('mapping_id')) or not nonempty(s.get('event'))
                or not isinstance(s.get('states'), list) or not s['states']
                or not all(nonempty(v) for v in s['states']) or type(s.get('initial_only', False)) is not bool):
            return None
    rule_keys = [(r['transition_id'], r['from_observed'], r['event'], r['to_observed']) for r in rules]
    stutter_keys = [(s['mapping_id'], s['event'], state) for s in stutters for state in s['states']]
    if (len({b['id'] for b in bindings}) != len(bindings) or len(set(rule_keys)) != len(rule_keys)
            or len(set(stutter_keys)) != len(stutter_keys)):
        return None
    stutter_rules = {(s['mapping_id'], s['event'], state): s.get('initial_only', False)
                     for s in stutters for state in s['states']}
    return bindings, set(rule_keys), stutter_rules


def assess_graph(graph, contract, bindings, rules, stutters):
    if (not isinstance(graph, dict) or graph.get('schema_version') != 'evidence-graph/v1'
            or not isinstance(graph.get('nodes'), list) or not isinstance(graph.get('links'), list)):
        return 'UNKNOWN', issue('GRAPH_INVALID')
    ids = {binding['id'] for binding in bindings}
    selected = defaultdict(list)
    for node in graph['nodes']:
        if isinstance(node, dict) and nonempty(node.get('id')) and node['id'] in ids:
            selected[node['id']].append(node)
    kind_revisions = {'CODE': 'code_revision', 'MODEL': 'model_revision', 'LEAN': 'model_revision',
                      'TRANSITION': 'model_revision', 'MAP': 'mapping_revision',
                      'VERIFIER': 'verifier_revision', 'TRACE': None}
    kinds = defaultdict(set)
    for binding in bindings:
        identifier = binding['id']
        if len(selected[identifier]) != 1:
            return 'UNKNOWN', issue('GRAPH_NODE_NOT_UNIQUE', id=identifier)
        node = selected[identifier][0]
        coordinate = node.get('resolved_coordinate')
        kind = node.get('kind')
        if not isinstance(kind, str) or kind not in kind_revisions:
            return 'UNKNOWN', issue('GRAPH_NODE_WRONG_KIND', id=identifier)
        if node.get('evidence_status') == 'STALE':
            return 'STALE', issue('GRAPH_NODE_STALE', id=identifier)
        if node.get('coordinate_valid') is not True or not isinstance(coordinate, dict):
            return 'UNKNOWN', issue('GRAPH_COORDINATE_UNVERIFIED', id=identifier)
        revision_field = kind_revisions[kind]
        if ((revision_field is not None and binding['revision'] != contract['revisions'][revision_field])
                or any(coordinate.get(key) != binding[key] for key in ('revision', 'sha256'))):
            return 'STALE', issue('GRAPH_BINDING_MISMATCH', id=identifier)
        kinds[kind].add(identifier)
    links = defaultdict(set)
    for link in graph['links']:
        if isinstance(link, dict) and all(nonempty(link.get(key)) for key in ('from', 'to', 'relation')):
            if link['from'] in ids and link['to'] in ids:
                links[(link['from'], link['relation'])].add(link['to'])
    supported_maps = {m for m in kinds['MAP'] if links[(m, 'points_to')] & kinds['CODE']}
    supported_steps = {t for t in kinds['TRANSITION'] if links[(t, 'implemented_by')] & supported_maps
                       and any(t in links[(m, 'defines')] for m in kinds['MODEL'])}
    for transition_id in sorted({r[0] for r in rules} - supported_steps):
        return 'UNKNOWN', issue('TRANSITION_GRAPH_CHAIN_MISSING', transition_id=transition_id)
    for mapping_id in sorted({s[0] for s in stutters} - supported_maps):
        return 'UNKNOWN', issue('STUTTER_GRAPH_CHAIN_MISSING', mapping_id=mapping_id)
    return None, None


def segment_parts(manifest):
    if (not isinstance(manifest, dict) or manifest.get('schema_version') != SEGMENT
            or not nonempty(manifest.get('trace_id')) or not nonempty(manifest.get('environment_profile'))
            or not revisions_valid(manifest.get('revisions')) or type(manifest.get('closed')) is not bool
            or manifest.get('collector_status') not in ('complete', 'partial', 'unknown')
            or not is_digest(manifest.get('raw_sha256')) or not is_digest(manifest.get('normalized_sha256'))):
        return None
    streams, initial = manifest.get('streams'), manifest.get('initial')
    if not isinstance(streams, list) or not isinstance(initial, dict):
        return None
    ranges = {}
    for s in streams:
        if (not isinstance(s, dict) or not nonempty(s.get('producer_id'))
                or not integer(s.get('producer_epoch')) or not integer(s.get('first_seq'), 1)
                or not integer(s.get('last_seq'), s['first_seq'])):
            return None
        stream = s['producer_id'], s['producer_epoch']
        if stream in ranges:
            return None
        ranges[stream] = s['first_seq'], s['last_seq']
    identities = set()
    for subject, start in initial.items():
        if (not nonempty(subject) or not isinstance(start, dict) or not nonempty(start.get('state'))
                or not identity_valid(start.get('identity'))):
            return None
        identity = tuple(sorted(start['identity'].items()))
        if identity in identities:
            return None
        identities.add(identity)
    return ranges, initial


def check_sequences(rows, ranges, raw_count):
    by_stream = defaultdict(list)
    for row in rows:
        by_stream[row['producer_id'], row['producer_epoch']].append(row)
    issues = []
    if not rows or not ranges or set(by_stream) != set(ranges):
        issues.append(issue('STREAM_ROSTER_MISMATCH'))
    if len(rows) != raw_count:
        issues.append(issue('RAW_ROW_COVERAGE_MISMATCH', expected=raw_count, observed=len(rows)))
    for event_id, count in sorted(Counter(row['event_id'] for row in rows).items()):
        if count != 1:
            issues.append(issue('EVENT_ID_REUSED', event_id=event_id))
    for raw_line, count in sorted(Counter(row['raw_line'] for row in rows).items()):
        if count != 1:
            issues.append(issue('RAW_ROW_REUSED', raw_line=raw_line))
    for stream, (first, last) in sorted(ranges.items()):
        stream_rows = by_stream[stream]
        stream_rows.sort(key=lambda row: row['seq'])
        if len(stream_rows) != last - first + 1 or any(
            row['seq'] != expected for expected, row in enumerate(stream_rows, first)
        ):
            issues.append(issue('SEQUENCE_GAP_OR_DUPLICATE', producer_id=stream[0],
                                producer_epoch=stream[1], first_seq=first, last_seq=last))
    return by_stream, issues


def causal_order(rows, by_stream):
    events = {row['event_id']: row for row in rows}
    parents = {identifier: set(r['causal_parent_ids']) for identifier, r in events.items()}
    missing = {identifier: sorted(ids - events.keys()) for identifier, ids in parents.items()
               if ids - events.keys()}
    if missing:
        return 'TRACE_INCOMPLETE', [issue('CAUSAL_PARENT_MISSING', event_id=i, parents=missing[i])
                                    for i in sorted(missing)], [], parents
    for stream_rows in by_stream.values():
        for predecessor, successor in zip(stream_rows, stream_rows[1:]):
            parents[successor['event_id']].add(predecessor['event_id'])
    children = defaultdict(list)
    incoming = {identifier: len(ids) for identifier, ids in parents.items()}
    for identifier, ids in parents.items():
        for parent in ids:
            children[parent].append(identifier)
    ready = [identifier for identifier, count in incoming.items() if not count]
    heapq.heapify(ready)
    order = []
    while ready:
        identifier = heapq.heappop(ready)
        order.append(identifier)
        for child in children[identifier]:
            incoming[child] -= 1
            if not incoming[child]:
                heapq.heappush(ready, child)
    if len(order) != len(events):
        return 'TRACE_DRIFTED', [issue('CAUSAL_CYCLE')], [], parents
    return None, [], order, parents


def precedes(earlier, later, parents, positions):
    todo = [later]
    visited = set()
    while todo:
        node = todo.pop()
        if earlier in parents[node]:
            return True
        candidates = {p for p in parents[node] if positions[p] > positions[earlier]} - visited
        todo.extend(candidates)
        visited.update(candidates)
    return False


def check_steps(rows, order, parents, initial, rules, stutters):
    events = {r['event_id']: r for r in rows}
    positions = {identifier: n for n, identifier in enumerate(order)}
    previous = {}
    for identifier in order:
        row = events[identifier]
        subject = row['subject_id']
        start = initial.get(subject)
        if start is None:
            return 'TRACE_INCOMPLETE', issue('INITIAL_STATE_MISSING', event_id=identifier, subject_id=subject)
        if row['identity'] != start['identity']:
            return 'TRACE_DRIFTED', issue('SUBJECT_IDENTITY_CHANGED', event_id=identifier, subject_id=subject)
        prior = previous.get(subject)
        if prior is not None and not precedes(prior, identifier, parents, positions):
            return 'UNKNOWN', issue('SUBJECT_ORDER_UNPROVEN', event_id=identifier, predecessor=prior)
        source, event, target = row['from_observed'], row['event'], row['to_observed']
        transition_id, mapping_id = row['transition_id'], row.get('stutter_mapping_id')
        if source is None or target is None or (transition_id is None and mapping_id is None):
            return 'UNKNOWN', issue('OBSERVATION_UNSUPPORTED', event_id=identifier, event=event)
        expected = start['state'] if prior is None else events[prior]['to_observed']
        if source != expected:
            return 'TRACE_DRIFTED', issue('SUBJECT_STATE_DISCONTINUITY', event_id=identifier,
                                          expected=expected, observed=source)
        if transition_id is not None and (transition_id, source, event, target) not in rules:
            return 'TRACE_DRIFTED', issue('TRANSITION_NOT_ALLOWED', event_id=identifier,
                                          transition_id=transition_id)
        if mapping_id is not None:
            stutter = (mapping_id, event, source)
            if source != target or stutter not in stutters or (stutters[stutter] and prior is not None):
                return 'TRACE_DRIFTED', issue('STUTTER_NOT_ALLOWED', event_id=identifier, mapping_id=mapping_id)
        previous[subject] = identifier
    return 'TRACE_CONFORMANT', None


def validate_trace(graph, contract, manifest, normalized_bytes, raw_bytes):
    """Assess one finite, caller-sealed segment. The caller supplies the trusted contract and collector metadata."""
    report = {'schema_version': REPORT, 'trace_id': None, 'raw_sha256': sha256(raw_bytes),
              'normalized_sha256': sha256(normalized_bytes), 'event_count': 0, 'event_order': [],
              'proof_status': 'NOT_ESTABLISHED', 'acceptance_status': 'NOT_ESTABLISHED'}

    def finish(status, *issues):
        return {**report, 'status': status, 'issues': list(issues)}

    parts = contract_parts(contract)
    if parts is None:
        return finish('UNKNOWN', issue('CONTRACT_INVALID'))
    bindings, rules, stutters = parts
    report['trace_id'] = contract['trace_id']
    schema_bytes = SCHEMA_PATH.read_bytes()
    actual_verifier = verifier_revision(schema_bytes)
    if contract['revisions']['verifier_revision'] != actual_verifier:
        return finish('STALE', issue('RUNNING_VERIFIER_MISMATCH', actual=actual_verifier))
    status, problem = assess_graph(graph, contract, bindings, rules, stutters)
    if problem:
        return finish(status, problem)
    segment = segment_parts(manifest)
    if segment is None:
        return finish('TRACE_INCOMPLETE', issue('SEGMENT_MANIFEST_INVALID'))
    ranges, initial = segment
    for field in ('trace_id', 'environment_profile', 'revisions'):
        if manifest[field] != contract[field]:
            return finish('STALE', issue('SEGMENT_CONTRACT_MISMATCH', field=field))
    for field in ('raw_sha256', 'normalized_sha256'):
        if manifest[field] != report[field]:
            return finish('STALE', issue('SEGMENT_HASH_MISMATCH', field=field))
    if not manifest['closed'] or manifest['collector_status'] == 'partial':
        return finish('TRACE_INCOMPLETE', issue('SEGMENT_NOT_CLOSED'))
    if manifest['collector_status'] != 'complete':
        return finish('UNKNOWN', issue('COLLECTOR_STATUS_UNKNOWN'))
    raw_lines = jsonl_lines(raw_bytes)
    for line_number, raw in enumerate(raw_lines, 1):
        try:
            if not isinstance(load_json(raw), dict):
                raise ValueError('raw event must be a JSON object')
        except (ValueError, RecursionError):
            return finish('TRACE_INCOMPLETE', issue('RAW_ROW_INVALID', raw_line=line_number))
    schema = read_schema(schema_bytes)
    rows = []
    revision_expectations = {'trace_id': contract['trace_id'],
                             'environment_profile': contract['environment_profile'], **contract['revisions']}
    for line_number, data in enumerate(jsonl_lines(normalized_bytes), 1):
        try:
            row = load_json(data)
        except (ValueError, RecursionError):
            return finish('TRACE_INCOMPLETE', issue('NORMALIZED_ROW_INVALID', line=line_number))
        if not event_schema_valid(row, schema):
            return finish('TRACE_INCOMPLETE', issue('NORMALIZED_SCHEMA_VIOLATION', line=line_number))
        mismatch = [k for k, v in revision_expectations.items() if row[k] != v]
        event_id, raw_line = row['event_id'], row['raw_line']
        if mismatch:
            return finish('STALE', issue('EVENT_CONTEXT_MISMATCH', event_id=event_id, fields=mismatch))
        if not row['segment_complete']:
            return finish('TRACE_INCOMPLETE', issue('EVENT_SEGMENT_OPEN', event_id=event_id))
        if raw_line > len(raw_lines):
            return finish('TRACE_INCOMPLETE', issue('RAW_ROW_MISSING', event_id=event_id, raw_line=raw_line))
        if row['payload_hash'] != sha256(raw_lines[raw_line - 1]):
            return finish('STALE', issue('RAW_ROW_HASH_MISMATCH', event_id=event_id, raw_line=raw_line))
        rows.append(row)
    report['event_count'] = len(rows)
    by_stream, issues = check_sequences(rows, ranges, len(raw_lines))
    if issues:
        return finish('TRACE_INCOMPLETE', *issues)
    for row in rows:
        if row.get('sequence_source') == 'observed_raw_line' and row['seq'] != row['raw_line']:
            return finish('TRACE_DRIFTED', issue('RAW_LINE_SEQUENCE_MISMATCH', event_id=row['event_id'],
                                                  raw_line=row['raw_line'], seq=row['seq']))
    status, issues, order, parents = causal_order(rows, by_stream)
    if issues:
        return finish(status, *issues)
    report['event_order'] = order
    status, problem = check_steps(rows, order, parents, initial, rules, stutters)
    return finish(status, *([problem] if problem else []))


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', required=True, type=Path)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--normalized', required=True, type=Path)
    parser.add_argument('--raw', required=True, type=Path)
    options = parser.parse_args(argv)
    try:
        graph = load_json(options.graph.read_bytes())
        contract = load_json(options.contract.read_bytes())
        manifest = load_json(options.manifest.read_bytes())
        report = validate_trace(graph, contract, manifest, options.normalized.read_bytes(), options.raw.read_bytes())
    except (OSError, ValueError, RecursionError) as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report['status'] == 'TRACE_CONFORMANT' else 1


if __name__ == '__main__':
    raise SystemExit(run())
