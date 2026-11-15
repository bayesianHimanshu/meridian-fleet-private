"""The tox stress fixtures (phase 5 step 1) are well formed: each spec builds, and each
ideal names a pre-registered check and a known endpoint form."""

import json
import re
from pathlib import Path

import pytest

from meridian.preclinical.synth import StudySpec, build

FIXTURES = sorted(Path("tests/fixtures/tox_stress").glob("*.json"))
IDEAL = re.compile(
    r"^(?:(?:dose_related_change|pairwise_change|dose_related_incidence|pairwise_incidence)"
    r":(?:lb:[A-Z0-9]+|bw:(?:BW|GAIN)|om:[A-Z, ]+:(?:abs|rel)|mi:[A-Z, ]+:[A-Z, ()]+|death)"
    r":[MF]:(?:main|recovery)|data_quality:[a-z_]+:.+)$"
)


def test_there_are_about_twelve_cases() -> None:
    assert 12 <= len(FIXTURES) <= 14


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_each_case_builds_and_names_known_checks(path: Path) -> None:
    case = json.loads(path.read_text())
    assert set(case) == {"case", "description", "spec", "ideal", "actual"}
    tables = build(StudySpec.model_validate(case["spec"]))
    assert {"dm", "tx", "ds", "bw", "lb", "om", "mi"} <= set(tables)
    assert case["ideal"] == sorted(case["ideal"])
    assert all(IDEAL.fullmatch(i) for i in case["ideal"]), case["ideal"]
