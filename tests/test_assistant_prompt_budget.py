from datetime import datetime

from mycelium.budget import count_message_tokens
from mycelium.models import WikiPage
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
        confidence=0.9,
        page_type="project",
        entity_id="project-orchid",
    )


def test_one_budget_bounds_system_recent_transcript_and_memory():
    record = {"transcript": [
        {"role": "user", "content": f"Old question {index} " * 12}
        if index % 2 == 0
        else {"role": "assistant", "content": f"Old answer {index} " * 12}
        for index in range(12)
    ]}
    budget = 400

    messages, selected_pages = build_chat_prompt(
        record,
        "What is the current Orchid decision?",
        [page("The Orchid launch decision is scheduled for Thursday.")],
        budget_tokens=budget,
    )

    assert count_message_tokens(messages) <= budget
    assert messages[-1]["content"] == "What is the current Orchid decision?"
    assert selected_pages[0].slug == "project-orchid"
    assert "Old question 0" not in "\n".join(item["content"] for item in messages)


def test_prompt_budget_truncates_oversized_current_message_from_the_front():
    current = "discarded beginning " * 200 + "essential final request"
    budget = 100

    messages, selected_pages = build_chat_prompt(
        {"transcript": []}, current, [], budget_tokens=budget
    )

    assert count_message_tokens(messages) <= budget
    assert messages[-1]["content"].endswith("essential final request")
    assert selected_pages == []


def test_prompt_budget_can_drop_memory_that_does_not_fit_after_recent_thread():
    record = {"transcript": [
        {"role": "user", "content": "Recent context " * 20},
        {"role": "assistant", "content": "Recent response " * 20},
    ]}

    messages, selected_pages = build_chat_prompt(
        record,
        "Continue.",
        [page("Large memory " * 300)],
        budget_tokens=180,
    )

    assert count_message_tokens(messages) <= 180
    assert selected_pages == []
