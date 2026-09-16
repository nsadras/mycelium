"""Attach registry metadata to resolved identity decisions."""


def planned_subjects(plan, registry, participants):
    """Attach exact registry metadata and local sequence IDs, without resolving meaning."""
    nodes = []
    for index, value in enumerate(plan["subjects"], 1):
        node = {**value, "node_id": f"n{index:03d}"}
        if node["resolution"] == "existing":
            entity = registry[node["entity_id"]]
            node.update(
                title=entity.title if node["title"] is None else node["title"],
                entity_type=entity.entity_type,
                candidate_entity_ids=[],
            )
        else:
            node["entity_id"] = ""
            if node["resolution"] == "new":
                node["candidate_entity_ids"] = []
        nodes.append(node)
    if "user" in plan:
        nodes.append(
            {
                **plan["user"],
                "node_id": "you",
                "entity_id": "you",
                "entity_type": "you",
                "resolution": "existing",
                "title": "You",
                "candidate_entity_ids": [],
            }
        )
    for node in nodes:
        # Exact declared speaker IDs carry the model's explicit identity binding.
        node["participant_evidence"] = [
            item for item in node["supporting_evidence"] if item in participants
        ]
    return nodes
