"""Failure grouping: cluster similar failures by root cause.

Usage (opt-in, not called by default):

    from grouping import group_failures, FailureGroup
    failure_groups = group_failures(failed_tests, test_map, parent_map)
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

try:
    from reporter import Test
except ImportError:
    from __main__ import Test  # type: ignore[import-untyped]


@dataclass
class FailureGroup:
    failing_keyword: str
    message_signature: str
    count: int
    tests: list[Test] = field(default_factory=list[Test])


def find_deepest_failure(
    test_elem: ET.Element, parent_map: dict[ET.Element, ET.Element]
) -> tuple[str, str]:
    """Locate the innermost failing keyword in a test element's tree.

    Walks the ``kw`` tree depth-first.  Picks the deepest ``kw`` whose status
    is ``FAIL`` *and* whose parent keyword is also failing (or whose parent is
    the ``<test>`` element itself).  Returns ``(keyword_name, message)``.
    """
    best_kw = ""
    best_msg = ""
    best_depth = -1

    def walk(elem: ET.Element, depth: int):
        nonlocal best_kw, best_msg, best_depth
        if elem.tag == "kw":
            status = elem.find("status")
            if status is not None and status.get("status") == "FAIL":
                parent = parent_map.get(elem)
                parent_fails = (
                    parent is not None
                    and parent.tag == "kw"
                    and (ps := parent.find("status")) is not None
                    and ps.get("status") == "FAIL"
                )
                parent_is_test = parent is not None and parent.tag == "test"
                if (parent_fails or parent_is_test) and depth > best_depth:
                    best_kw = elem.get("name", "")
                    best_msg = (status.text or "").strip()
                    best_depth = depth
        for child in elem:
            walk(child, depth + 1)

    walk(test_elem, 0)
    if not best_kw:
        status = test_elem.find("status")
        if status is not None and status.get("status") == "FAIL":
            best_kw = "(test level)"
            best_msg = (status.text or "").strip()
    return best_kw, best_msg


def normalize_message(message: str) -> str:
    """Reduce a failure message to a stable signature for grouping.

    Strips stacktraces, replaces locator values / hex addresses / numbers
    with placeholders, and collapses whitespace.
    """
    msg = re.sub(r"\bStacktrace:.*$", "", message, flags=re.DOTALL)
    msg = re.sub(r"'[^']*(?:css|xpath|id|name|class):[^']*'", "'LOCATOR'", msg)
    msg = re.sub(r"\b0x[0-9a-fA-F]+\b", "0xN", msg)
    msg = re.sub(r"\b\d{1,3}(?:,?\d{3})*(?:\.\d+)?\b", "N", msg)
    msg = re.sub(r"after \d+ seconds", "after N seconds", msg)
    msg = re.sub(r"\s+", " ", msg).strip()
    return msg


def group_failures(
    failed_tests: list[Test],
    test_map: dict[str, ET.Element],
    parent_map: dict[ET.Element, ET.Element],
) -> list[FailureGroup]:
    """Cluster *failed_tests* by their deepest failing keyword + normalized message.

    Returns groups sorted by count descending.
    """
    groups: dict[tuple[str, str], FailureGroup] = {}
    for test in failed_tests:
        test_elem = test_map.get(test.name)
        if test_elem is None:
            continue
        kw_name, msg = find_deepest_failure(test_elem, parent_map)
        sig = normalize_message(msg)
        key = (kw_name, sig)
        if key not in groups:
            groups[key] = FailureGroup(
                failing_keyword=kw_name,
                message_signature=sig,
                count=0,
            )
        groups[key].count += 1
        groups[key].tests.append(test)
    return sorted(groups.values(), key=lambda g: g.count, reverse=True)
