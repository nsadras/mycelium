"""Non-blocking taxonomy enrichment for already-formed wiki pages."""

from __future__ import annotations

from dataclasses import dataclass, field

from mycelium.models import PageType, WikiPage
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import page_taxonomy_output_model


@dataclass
class PageTaxonomyResult:
    assignments: dict[str, PageType] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)


class PageTaxonomist:
    """Classify page identity without changing page formation or claim placement."""

    batch_size = 8
    evidence_chars = 3000

    def __init__(self, llm: OllamaClient):
        self.llm = llm

    async def classify(self, pages: list[WikiPage]) -> PageTaxonomyResult:
        result = PageTaxonomyResult()
        candidates = sorted(
            (page for page in pages if page.page_type is None),
            key=lambda page: page.slug,
        )
        for page in candidates:
            if page.slug == "user-profile":
                result.assignments[page.slug] = "you"

        candidates = [page for page in candidates if page.slug != "user-profile"]
        for offset in range(0, len(candidates), self.batch_size):
            batch = candidates[offset:offset + self.batch_size]
            batch_result = await self._classify_batch(batch)
            result.assignments.update(batch_result.assignments)
            result.failures.extend(batch_result.failures)
        return result

    async def _classify_batch(self, pages: list[WikiPage]) -> PageTaxonomyResult:
        aliases = {f"P{index:03d}": page for index, page in enumerate(pages, start=1)}
        output_model = page_taxonomy_output_model(aliases)
        system = """Classify each already-formed personal-memory wiki page by what the page itself
represents. Taxonomy is descriptive only: do not propose new pages, rename pages, split pages, merge
pages, or infer relationships.

Use exactly one type:
- person: a specific human other than the user
- project: a concrete endeavor with an objective, work, or intended outcome
- topic: a subject, interest, practice, preference area, or recurring theme
- organization: a company, institution, team, or community
- place: a geographic location or physical venue
- event: one bounded occurrence
- you: the memory owner's profile (normally reserved for user-profile)

Prefer project over topic when the page describes ongoing work toward an outcome. Prefer topic over
event for recurring activities. Classify the existing page identity, not every noun mentioned in its
claims. The routing_kind is a coarse placement hint, not a valid final type: entity usually narrows
to person, organization, or place; topic usually narrows to project or topic; event usually remains
event. Prefer the named entity represented by the title over an activity involving that entity.
Return JSON satisfying the supplied schema only."""
        blocks = []
        for alias, page in aliases.items():
            body = page.content.strip()[:self.evidence_chars]
            routing_kind = next(
                (
                    tag.removeprefix("page-type-")
                    for tag in page.tags
                    if tag.startswith("page-type-")
                ),
                "unknown",
            )
            blocks.append(
                f"[PAGE {alias}]\nslug={page.slug}\ntitle={page.title}\n"
                f"routing_kind={routing_kind}\ncontent:\n{body or '(empty)'}"
            )
        try:
            response = await self.llm.call_structured(
                system,
                "\n\n".join(blocks),
                output_model,
                num_predict=1024,
                debug_label="dream-page-taxonomy",
            )
            if not isinstance(response, dict):
                raise ValueError("Taxonomy response was not an object")
            decisions = output_model.model_validate(response).model_dump()
        except Exception as exc:
            return PageTaxonomyResult(failures=[{
                "page_slugs": ",".join(page.slug for page in pages),
                "reason": (
                    "Page taxonomy response did not satisfy the contract: "
                    f"{type(exc).__name__}"
                ),
            }])

        return PageTaxonomyResult(assignments={
            aliases[alias].slug: decision["page_type"]
            for alias, decision in decisions.items()
        })
