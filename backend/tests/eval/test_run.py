import pytest

from geniai.eval.run import EvalConfigError, load_candidates


@pytest.mark.parametrize("raw", ["", "[]", "not json", '[{"label": "x"}]'])
def test_rejects_missing_or_invalid_candidates_with_a_clear_error(raw: str) -> None:
    with pytest.raises(EvalConfigError, match="EVAL_CANDIDATES"):
        load_candidates({"EVAL_CANDIDATES": raw})


def test_reads_the_documented_json_shape() -> None:
    raw = '[{"label":"candidate-a","baseUrl":"https://llm.example.com/v1","model":"model-a","apiKeyEnv":"KEY_A"}]'
    [candidate] = load_candidates({"EVAL_CANDIDATES": raw})
    assert (candidate.label, candidate.model, candidate.apiKeyEnv) == ("candidate-a", "model-a", "KEY_A")
    assert candidate.extraBody is None
