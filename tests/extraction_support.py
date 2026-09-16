"""Author explicit per-segment decisions for structural pipeline tests."""


def extraction_response(claims, source_only_segment_ids=()):
    segments = {}
    support_ids = set()
    for claim in claims:
        primary, *support = claim["segment_ids"]
        segments.setdefault(primary, {"claims": []})["claims"].append({**claim, "segment_ids": support})
        support_ids.update(support)
    for sid in support_ids:
        segments.setdefault(sid, None)
    for sid in source_only_segment_ids:
        if sid in segments:
            raise ValueError("Conflicting fixture decisions for one segment")
        segments[sid] = None
    return {"segments": segments}


def time_details(segment_id, expression, meaning, *, role='event_time', target='The stated action'):
    return {'times': [{'expression': expression, 'target': target, 'role': role,
                       'evidence_segment_id': segment_id, 'meaning': meaning}], 'inference_basis': None}


def stored_time(segment_id, expression, meaning, anchor, *, role='event_time', target='The stated action'):
    from mycelium.temporal import normalize_temporal_facets
    return normalize_temporal_facets(time_details(segment_id, expression, meaning, role=role, target=target),
                                     {segment_id: anchor})
