"""Neutral annotated search controls, shared by native and scale diagnostics."""


def record(cid, text, entity=None, surface=None):
    refs = (
        []
        if entity is None
        else [
            {
                "role": "subject",
                "surface": surface,
                "entity_id": entity,
                "confidence": 0.9,
                "reason": "The source describes this subject.",
                "origin": "scope",
                "identity_decision_id": None,
            }
        ]
    )
    return dict(
        claim_id=cid,
        text=text,
        about=[],
        temporal=[],
        temporal_status="unknown",
        identity_bindings=refs,
        citations=[
            {
                "source_id": "source-" + cid,
                "segment_id": "line-" + cid,
                "source_time": "2031-05-06",
                "speaker": "Source",
                "text": text,
            }
        ],
        withdrawn_citations=[],
    )


def controls():
    records = {}
    incoming = []
    annotations = []
    pairs = [
        (
            "reschedule",
            "Mara will deliver the draft on Friday.",
            "Mara corrected the draft delivery plan: Monday replaces Friday.",
            "mara",
            "Mara",
            "right_supersedes_left",
            False,
        ),
        (
            "same_batch",
            "The hall reservation for the concert on 2031-06-07 costs 80 euros.",
            "The hall reservation for the same concert on 2031-06-07 costs 120 euros.",
            "concert",
            "concert on 2031-06-07",
            "contradicts",
            True,
        ),
        (
            "renamed",
            "The inventory project has no name yet.",
            "The same inventory project is now named Cedar.",
            "inventory",
            "inventory project",
            "right_supersedes_left",
            False,
        ),
        (
            "unplaced",
            "Inez lives at the Oslo apartment.",
            "Inez moved out of the Oslo apartment and now lives at the Bergen apartment.",
            None,
            None,
            "right_supersedes_left",
            False,
        ),
        (
            "ambiguous_identity",
            "Alex is a nurse living in Oslo.",
            "Alex, whose identity was not specified, said they live in Bergen.",
            None,
            None,
            "no_change",
            False,
        ),
        (
            "independent_events",
            "Mara visited a museum in May 2028.",
            "Mara visited a museum in May 2029.",
            "mara",
            "Mara",
            "no_change",
            False,
        ),
        (
            "tentative",
            "Jules lives in Porto.",
            "Jules is considering a move to Zagreb but has not decided.",
            "jules",
            "Jules",
            "no_change",
            False,
        ),
    ]
    for name, left, right, entity, surface, expected, same_batch in pairs:
        a, b = name + "-old", name + "-new"
        records[a] = record(a, left, entity, surface)
        records[b] = record(b, right, entity, surface)
        incoming.append(b)
        if same_batch:
            incoming.append(a)
        annotations.append(
            dict(
                case=name,
                left=a,
                right=b,
                expected=expected,
                critical=expected != "no_change",
            )
        )
    people = [
        "Nora",
        "Ivo",
        "Leena",
        "Mateo",
        "Mina",
        "Owen",
        "Lara",
        "Theo",
        "Jun",
        "Esme",
    ]
    topics = [
        "practices the cello on Saturdays",
        "prefers written progress reports",
        "maintains a bicycle for commuting",
        "is learning to bake sourdough",
        "volunteers in a public garden",
        "collects antique maps",
        "studies marine biology",
        "restores wooden furniture",
        "teaches beginner photography",
    ]
    for i, person in enumerate(people):
        for j, topic in enumerate(topics):
            cid = f"background-{i}-{j}"
            records[cid] = record(cid, f"{person} {topic}.", "person-" + person, person)
    return records, incoming, annotations
