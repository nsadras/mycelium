from benchmarks.mycelium_bench.scoring import token_f1


def test_token_f1_normalizes_iso_and_written_dates():
    assert token_f1("2023-01-29", "29 January, 2023") == 1.0


def test_token_f1_handles_basic_inflection_without_semantic_judging():
    assert token_f1("one of my trophies", "a trophy") > 0.0
    assert token_f1("excited", "excitement") == 1.0
    assert token_f1("Jon dances; Gina dances", "by dancing") > 0.0
