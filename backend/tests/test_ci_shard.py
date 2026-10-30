import os
from pathlib import Path
import subprocess
import sys

import pytest

from ci_shard import assign_shards


def test_assigns_each_file_once_and_balances_collected_cases():
    nodeids = [
        "tests/test_a.py::test_one[1]",
        "tests/test_a.py::test_one[2]",
        "tests/test_a.py::test_one[3]",
        "tests/test_b.py::test_two",
        "tests/test_c.py::test_three",
        "tests/test_d.py::test_four",
        "tests/test_e.py::test_five",
        "tests/test_f.py::test_six",
    ]
    assignments = assign_shards(nodeids, 5)
    assert assignments == {
        "tests/test_a.py": 1,
        "tests/test_b.py": 2,
        "tests/test_c.py": 3,
        "tests/test_d.py": 4,
        "tests/test_e.py": 5,
        "tests/test_f.py": 2,
    }
    assert assignments == assign_shards(list(reversed(nodeids)), 5)
    for nodeid in nodeids:
        assert assignments[nodeid.split("::", 1)[0]] in (1, 2, 3, 4, 5)


def test_new_test_files_are_assigned_and_invalid_counts_are_rejected():
    nodeids = ["tests/test_a.py::test_one", "new/test_other.py::test_two"]
    assert set(assign_shards(nodeids, 5)) == {"tests/test_a.py", "new/test_other.py"}
    with pytest.raises(ValueError, match="positive"):
        assign_shards(nodeids, 0)


def test_pytest_shards_collect_each_case_once_and_reject_invalid_options(tmp_path):
    for name, count in (("a", 3), ("b", 2), ("c", 1), ("d", 1), ("e", 1)):
        source = "".join(f"def test_case_{index}():\n    pass\n" for index in range(count))
        (tmp_path / f"test_{name}.py").write_text(source, encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    base = [sys.executable, "-m", "pytest", "-q", "--collect-only", "-p", "ci_shard"]

    def collect(*options):
        return subprocess.run([*base, *options], cwd=tmp_path, env=env, text=True, capture_output=True)

    full = collect()
    assert full.returncode == 0, full.stderr
    all_cases = [line for line in full.stdout.splitlines() if "::" in line]
    shards = []
    for index in range(1, 6):
        result = collect("--ci-shard", str(index), "--ci-shards", "5")
        assert result.returncode == 0, result.stderr
        shards.append([line for line in result.stdout.splitlines() if "::" in line])
    assert len(all_cases) == 8
    assert sorted(case for shard in shards for case in shard) == sorted(all_cases)
    assert all(shards)
    assert collect("--ci-shard", "6", "--ci-shards", "5").returncode == 4
    assert collect("--ci-shard", "1").returncode == 4


def test_shard_keeps_test_failures_visible(tmp_path):
    (tmp_path / "test_failure.py").write_text("def test_failure():\n    assert False\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "ci_shard", "--ci-shard", "1", "--ci-shards", "1"],
        cwd=tmp_path, env=env, text=True, capture_output=True,
    )
    assert result.returncode == 1
    assert "test_failure" in result.stdout
