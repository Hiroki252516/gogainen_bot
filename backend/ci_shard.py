"""Distribute collected tests by file across independent CI runners."""

from collections import Counter

import pytest


def assign_shards(nodeids: list[str], shard_count: int) -> dict[str, int]:
    """Assign each file once, balancing by collected test count."""
    if shard_count < 1:
        raise ValueError("shard count must be positive")

    counts = Counter(nodeid.split("::", 1)[0] for nodeid in nodeids)
    loads = [0] * shard_count
    assignments: dict[str, int] = {}
    for path, count in sorted(counts.items(), key=lambda entry: (-entry[1], entry[0])):
        shard = min(range(shard_count), key=lambda index: (loads[index], index))
        assignments[path] = shard + 1
        loads[shard] += count
    return assignments


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CI sharding")
    group.addoption("--ci-shard", type=int, default=None, help="One-based CI shard index")
    group.addoption("--ci-shards", type=int, default=None, help="Total number of CI shards")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    shard = config.getoption("--ci-shard")
    shard_count = config.getoption("--ci-shards")
    if shard is None and shard_count is None:
        return
    if shard_count is None or shard is None or not 1 <= shard <= shard_count:
        raise pytest.UsageError("--ci-shard and --ci-shards must specify 1 <= shard <= shard count")

    assignments = assign_shards([item.nodeid for item in items], shard_count)
    selected, deselected = [], []
    for item in items:
        target = selected if assignments[item.nodeid.split("::", 1)[0]] == shard else deselected
        target.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected
