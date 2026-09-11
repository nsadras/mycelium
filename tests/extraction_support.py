"""Author explicit per-segment decisions for structural pipeline tests."""


def extraction_response(claims, source_only_segment_ids=()):
    segments = {}
    support_ids = set()
    for claim in claims:
        primary, *support = claim["segment_ids"]
        segments.setdefault(primary, {"claims": []})["claims"].append({**claim, "segment_ids": support})
        support_ids.update(support)
    for sid in support_ids:
        segments.setdefault(sid, {"reason": "Evidence supporting another segment's statement."})
    for sid in source_only_segment_ids:
        if sid in segments:
            raise ValueError("Conflicting fixture decisions for one segment")
        segments[sid] = {"reason": "The segment contains no new assertion."}
    return {"segments": segments}
