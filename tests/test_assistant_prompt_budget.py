from mycelium.budget import count_message_tokens
from dataclasses import replace
from mycelium.operations import EvidenceRecord, MemoryEvidence
from server.api.sessions import build_chat_prompt


def evidence_for(statement: str) -> MemoryEvidence:
    return MemoryEvidence(
        records=(
            EvidenceRecord(
                record_id="claim-orchid",
                record_type="claim",
                statement=statement,
                subject_entity_id="project-orchid",
                subject_name="Project Orchid",
                claim_ids=("claim-orchid",),
            ),
        )
    )


def test_one_budget_bounds_system_recent_transcript_and_memory():
    record = {
        "transcript": [
            {"role": "user", "content": f"Old question {index} " * 12}
            if index % 2 == 0
            else {"role": "assistant", "content": f"Old answer {index} " * 12}
            for index in range(12)
        ]
    }
    budget = 650

    memory_page = "The Orchid launch decision is scheduled for Thursday."
    messages, selected_evidence, fitted_request = build_chat_prompt(
        record,
        "What is the current Orchid decision?",
        evidence_for(memory_page),
        budget_tokens=budget,
        workspace_search_limit=3,
        workspace_evidence_budget_tokens=6000,
    )

    assert count_message_tokens(messages) <= budget
    assert selected_evidence.records[0].record_id == "claim-orchid"
    assert fitted_request == "What is the current Orchid decision?"


def test_prompt_budget_accepts_an_oversized_current_message():
    current = "discarded beginning " * 200 + "essential final request"
    budget = 400

    messages, selected_evidence, fitted_request = build_chat_prompt(
        {"transcript": []},
        current,
        MemoryEvidence(),
        budget_tokens=budget,
        workspace_search_limit=3,
        workspace_evidence_budget_tokens=6000,
    )

    assert count_message_tokens(messages) <= budget
    assert selected_evidence.records == ()
    assert fitted_request.endswith("essential final request")
    assert fitted_request != current


def test_prompt_budget_can_drop_memory_that_does_not_fit_after_recent_thread():
    record = {
        "transcript": [
            {"role": "user", "content": "Recent context " * 20},
            {"role": "assistant", "content": "Recent response " * 20},
        ]
    }

    memory_page = "Large memory " * 300
    messages, selected_evidence, fitted_request = build_chat_prompt(
        record,
        "Continue.",
        evidence_for(memory_page),
        budget_tokens=400,
        workspace_search_limit=3,
        workspace_evidence_budget_tokens=6000,
    )

    assert count_message_tokens(messages) <= 400
    assert selected_evidence.records == ()
    assert fitted_request == "Continue."


def test_prompt_fits_individual_unowned_and_same_subject_records():
    small = evidence_for("The meeting starts at noon.").records[0]
    large = replace(small, record_id="claim-large", statement="Lengthy detail " * 1000)
    unowned = replace(
        small,
        record_id="claim-unowned",
        subject_entity_id=None,
        subject_name=None,
        claim_ids=("claim-unowned",),
    )
    evidence = MemoryEvidence(records=(large, small, unowned))

    messages, selected, _ = build_chat_prompt(
        {"transcript": []},
        "When is the meeting?",
        evidence,
        budget_tokens=650,
        workspace_search_limit=3,
        workspace_evidence_budget_tokens=6000,
    )

    assert selected.records == (small, unowned)
    assert selected.more_available
    assert count_message_tokens(messages) <= 650
    assert "claim-large" not in messages[-1]["content"]
    assert "claim-unowned" in messages[-1]["content"]
