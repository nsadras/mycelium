"""Neutral evaluation inputs for the current identity-review probes."""

CASES = [
    (
        "person_and_new_project",
        "Rin Patel leads Orchard, an ongoing toolchain upgrade project.",
        {"person-rin": ("person", "Rin Patel")},
        [("person-rin", "Rin Patel")],
        {"person-rin"},
        {"project"},
    ),
    (
        "two_reviewed_subjects",
        "Rin Patel leads Orchard, an ongoing toolchain upgrade project.",
        {
            "person-rin": ("person", "Rin Patel"),
            "project-orchard": ("project", "Orchard"),
        },
        [("person-rin", "Rin Patel"), ("project-orchard", "Orchard")],
        {"person-rin", "project-orchard"},
        set(),
    ),
    (
        "person_and_colleague",
        "Rin Patel and Casey Wells organize a workshop together.",
        {"person-rin": ("person", "Rin Patel")},
        [("person-rin", "Rin Patel")],
        {"person-rin"},
        {"person"},
    ),
    (
        "shared_surface_different_kinds",
        "Nora, the person, maintains a software project also called Nora.",
        {"project-nora": ("project", "Nora")},
        [("project-nora", "software project called Nora")],
        {"project-nora"},
        {"person"},
    ),
]
