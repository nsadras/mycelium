"""Build explicit discovery fixtures; native probes establish model behavior."""

from copy import deepcopy


def discovery_response(payload):
    result = deepcopy(payload)
    result["participant_subjects"] = {}
    for index, subject in enumerate(result["subjects"], 1):
        subject["subject_id"] = f"S{index:03d}"
        support = []
        for alias in subject["supporting_evidence"]:
            if alias.startswith("P"):
                assert alias not in result["participant_subjects"]
                result["participant_subjects"][alias] = {
                    "subject_id": subject["subject_id"]
                }
            else:
                support.append(alias)
        subject["supporting_evidence"] = support
    return result
