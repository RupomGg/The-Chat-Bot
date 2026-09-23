"""Checks the CI workflow file locally, since GitHub Actions can't run on this machine."""

import pathlib
import re
import tomllib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEXT = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
WORKFLOW = yaml.safe_load(TEXT)
JOB = WORKFLOW["jobs"]["gate"]
RUN = "\n".join(step.get("run", "") for step in JOB["steps"])
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
# ikalnytskyi/action-setup-postgres v8
SETUP_POSTGRES_SHA = "c4dda34aae1c821e3a771b68b73b13af3198a7ee"


def step_using(prefix):
    return next(s for s in JOB["steps"] if s.get("uses", "").startswith(prefix))


def test_runs_on_every_push_and_pull_request():
    # PyYAML reads the bare key `on` as boolean True.
    triggers = WORKFLOW[True]
    assert "push" in triggers
    assert "pull_request" in triggers
    assert triggers["push"] is None  # no branch filter: every branch is checked


def test_runs_on_linux_windows_and_macos():
    assert JOB["runs-on"] == "${{ matrix.os }}"
    assert sorted(JOB["strategy"]["matrix"]["os"]) == [
        "macos-latest",
        "ubuntu-latest",
        "windows-latest",
    ]
    assert JOB["strategy"]["fail-fast"] is False  # one OS failing still shows the others


def test_same_shell_on_every_os():
    assert JOB["defaults"]["run"]["shell"] == "bash"


def test_python_version_matches_pyproject():
    ci_version = step_using("actions/setup-python")["with"]["python-version"]
    assert PYPROJECT["project"]["requires-python"] == f">={ci_version},<3.14"


def test_postgres_18_on_every_os_via_pinned_action():
    step = step_using("ikalnytskyi/action-setup-postgres")
    assert step["uses"] == f"ikalnytskyi/action-setup-postgres@{SETUP_POSTGRES_SHA}"
    assert step["with"]["postgres-version"] == "18"  # same major version as local (D-008)
    assert "services" not in JOB  # service containers only exist on Linux runners


def test_tests_use_a_limited_login_like_local():
    # The action's user is a superuser; tests must not rely on superuser powers (O-004).
    assert "CREATE ROLE chatbot_test LOGIN CREATEDB NOSUPERUSER PASSWORD" in RUN
    assert "SUPERUSER" not in RUN.replace("NOSUPERUSER", "")
    assert JOB["env"]["TEST_DATABASE_URL"].startswith("postgresql://chatbot_test:")
    assert "@localhost:5432/" in JOB["env"]["TEST_DATABASE_URL"]


def test_every_gate_command_is_present():
    assert "python -m ruff check ." in RUN
    assert "python -m ruff format --check ." in RUN
    assert re.search(r"^python -m pytest -q$", RUN, re.M)
    assert "python -m coverage run -m pytest -q" in RUN
    assert "sort -r" in RUN


def test_coverage_drop_fails_the_job():
    assert "coverage report --fail-under=100" in RUN


def test_no_step_hides_failures():
    for step in JOB["steps"]:
        assert not step.get("continue-on-error", False)
        assert "|| true" not in step.get("run", "")


def test_no_secrets_required():
    assert "secrets." not in TEXT


def test_third_party_actions_are_pinned_to_a_commit():
    for step in JOB["steps"]:
        uses = step.get("uses", "")
        if uses and not uses.startswith("actions/"):
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uses), uses


def test_least_privilege_and_bounded_runtime():
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert 0 < JOB["timeout-minutes"] <= 30


def test_warnings_are_errors_in_config_used_by_ci():
    filters = PYPROJECT["tool"]["pytest"]["ini_options"]["filterwarnings"]
    assert filters[0] == "error"
    assert "-W" not in RUN  # a command-line -W would override the narrow ignores


def test_coverage_measures_branches():
    assert PYPROJECT["tool"]["coverage"]["run"]["branch"] is True
