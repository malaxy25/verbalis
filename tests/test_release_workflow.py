"""The release workflow: only after green tests, only for a new version, exactly the tested commit."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
JOBS = WORKFLOW["jobs"]


TESTS = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))


def test_release_waits_for_exactly_the_tests_workflow():
    """The release workflow finds the tests by name – renaming only one of them would silently stop
    all releases."""
    assert WORKFLOW[True]["workflow_run"]["workflows"] == [TESTS["name"]]


def test_tests_run_once_per_push_to_main_and_for_pull_requests():
    triggers = TESTS[True]
    assert triggers["push"] == {"branches": ["main"]}   # not again for the tag the release creates
    assert "pull_request" in triggers


def test_release_starts_after_tests_not_on_tags():
    triggers = WORKFLOW[True]                     # YAML reads the key «on» as True
    assert triggers["workflow_run"]["types"] == ["completed"]
    assert "push" not in triggers                 # a pushed tag no longer releases untested code
    condition = JOBS["version"]["if"]
    for part in ("conclusion == 'success'", "event == 'push'", "head_branch == 'main'"):
        assert part in condition


def test_every_job_builds_the_tested_commit():
    for name in ("windows", "macos", "publish"):
        checkout = next(s for s in JOBS[name]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
        assert checkout["with"]["ref"] == "${{ needs.version.outputs.sha }}", name


def test_tag_only_after_a_successful_windows_build():
    publish = JOBS["publish"]
    assert "needs.windows.result == 'success'" in publish["if"]
    assert "needs.version.outputs.release == 'true'" in publish["if"]
    names = [s.get("name", "") for s in publish["steps"]]
    assert names.index("Create the version tag on the tested commit") < names.index("Publish GitHub Release")


@pytest.mark.skipif(sys.platform == "win32", reason="the decision step is a bash script")
@pytest.mark.parametrize("version, changelog, expected", [
    ("1.0.0", True, "release=false"),    # tag exists already: nothing to do
    ("1.0.1", True, "release=true"),     # new version with changelog: release
    ("1.0.1", False, None),              # new version without changelog: the run fails
])
def test_decision_step(tmp_path, version, changelog, expected):
    run = lambda *a, cwd: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True)
    origin = tmp_path / "origin.git"
    run("git", "init", "-q", "--bare", str(origin), cwd=tmp_path)
    work = tmp_path / "work"
    run("git", "clone", "-q", str(origin), str(work), cwd=tmp_path)
    (work / "src" / "verbalis").mkdir(parents=True)
    (work / "src" / "verbalis" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    (work / "CHANGELOG.md").write_text(f"# Changelog\n\n## {version} – 2026-10-10\n- x\n" if changelog else "# Changelog\n")
    for cmd in (["git", "add", "-A"], ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
                ["git", "tag", "v1.0.0"], ["git", "push", "-q", "origin", "HEAD", "--tags"]):
        run(*cmd, cwd=work)
    output = tmp_path / "out"
    output.write_text("")
    script = JOBS["version"]["steps"][1]["run"]
    result = subprocess.run(["bash", "-c", script], cwd=work, capture_output=True, text=True,
                            env={"GITHUB_OUTPUT": str(output), "EVENT": "workflow_run", "SHA": "abc",
                                 "PATH": "/usr/bin:/bin:/usr/local/bin"})
    if expected is None:
        assert result.returncode != 0 and "CHANGELOG.md has no section" in result.stdout
    else:
        assert result.returncode == 0 and expected in output.read_text()
