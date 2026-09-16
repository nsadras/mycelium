"""Explicit neutral decisions for lifecycle mechanics; native probes prove semantics."""
import json


def lifecycle_response(_system, user, schema, **kwargs):
    stage = kwargs.get('debug_label')
    if stage == 'memory-correction':
        return {'about': [{'entity': 'user', 'role': 'subject'}], 'claim_type': 'preference',
                'predicate': None, 'temporal_status': 'atemporal',
                'facets': {'times': [], 'inference_basis': None}}
    if stage == 'dream-identity-plan':
        return {'subjects': [{'resolution': 'existing', 'entity_id': 'you', 'title': None, 'reason': 'The statement concerns the user.', 'supporting_evidence': ['C001'], 'aliases': []}]}
    if stage == 'dream-claim-routing':
        return {'decisions': {a: {"prominence": "briefing", 'pages': {'you': {'section_key': 'preferences_working_style', 'reason': 'User preference.'}},
                                 'owner_entity': 'you', 'reason': None, 'uncertainty': None}
                for a in schema.model_fields['decisions'].annotation.model_fields}}
    if stage == 'dream-fact-candidate-selection':
        return {'decisions': {a: {'candidate_fact_ids': [], 'reason': 'Independent fixture claim.'}
                for a in schema.model_fields['decisions'].annotation.model_fields}}
    if stage == 'dream-fact-synthesis':
        claims = json.loads(user.split('CANONICAL STORED CLAIMS\n', 1)[1].split('\n\nEXISTING DISPLAY FACTS', 1)[0])
        return {'facts': [{'member_claim_aliases': [a], 'text': None, 'memory_scope': 'An independent fixture statement.',
                           'state': 'current', 'section_key': 'preferences_working_style', 'prominence': 'briefing'} for a in claims]}
    raise AssertionError(f'Unexpected lifecycle model call: {stage}')
