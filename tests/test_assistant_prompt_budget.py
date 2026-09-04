from datetime import datetime

from mycelium.budget import count_message_tokens
from mycelium.models import WikiPage
from mycelium.operations import EvidenceRecord, MemoryEvidence
from server.api.sessions import build_chat_prompt


def page(content: str) -> WikiPage:
    now = datetime.now()
    return WikiPage(
        slug="project-orchid",
        title="Project Orchid",
        content=content,
        created=now,
        last_updated=now,
        version=1,
        page_type="project",
        entity_id="project-orchid",
    )


def evidence_for(page_value: WikiPage) -> MemoryEvidence:
    return MemoryEvidence(
        records=(
            EvidenceRecord(
                record_id=f"claim-{page_value.slug}",
                record_type="claim",
                statement=page_value.content,
                subject_entity_id=page_value.entity_id,
                subject_name=page_value.title,
                claim_ids=(f"claim-{page_value.slug}",),
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

    memory_page = page("The Orchid launch decision is scheduled for Thursday.")
    messages, selected_pages, fitted_request = build_chat_prompt(
        record,
        "What is the current Orchid decision?",
        [memory_page],
        evidence_for(memory_page),
        budget_tokens=budget,
        workspace_search_limit=3,
        workspace_evidence_budget_tokens=6000,
    )

    assert count_message_tokens(messages) <= budget
    assert selected_pages[0].slug == "project-orchid"
    assert fitted_request == "What is the current Orchid decision?"


def test_prompt_budget_accepts_an_oversized_current_message():
    current = "discarded beginning " * 200 + "essential final request"
    budget = 400

    messages, selected_pages, fitted_request = build_chat_prompt(
        {"transcript": []},
        current,
        [],
        MemoryEvidence(),
        budget_tokens=budget,
        workspace_search_limit=3,
        workspace_evidence_budget_tokens=6000,
    )

    assert count_message_tokens(messages) <= budget
    assert selected_pages == []
    assert fitted_request.endswith("essential final request")
    assert fitted_request != current


def test_prompt_budget_can_drop_memory_that_does_not_fit_after_recent_thread():
    record = {
        "transcript": [
            {"role": "user", "content": "Recent context " * 20},
            {"role": "assistant", "content": "Recent response " * 20},
        ]
    }

    memory_page = page("Large memory " * 300)
    messages, selected_pages, fitted_request = build_chat_prompt(
        record,
        "Continue.",
        [memory_page],
        evidence_for(memory_page),
        budget_tokens=400,
        workspace_search_limit=3,
        workspace_evidence_budget_tokens=6000,
    )

    assert count_message_tokens(messages) <= 400
    assert selected_pages == []
    assert fitted_request == "Continue."
