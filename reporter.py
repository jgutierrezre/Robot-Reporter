#!/usr/bin/env python3
"""Robot Reporter - Parse Robot Framework output.xml and post results to GitHub step summary."""

import argparse
import datetime
import html
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import cast

import yaml

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "templates")

log = logging.getLogger(__name__)


@dataclass
class Args:
    report_path: str
    show_passed_tests: str
    failed_tests_on_top: str
    report_type: str
    history_path: str
    test_tags: str
    run_parallel: str
    thread_count: str
    test_path: str


@dataclass
class Test:
    test_id: str
    name: str
    status: str
    suite: str
    execution_time: float
    message: str
    tags: str


@dataclass
class FailureGroup:
    failing_keyword: str
    message_signature: str
    count: int
    tests: list[Test] = field(default_factory=list[Test])


@dataclass
class Report:
    passed: int
    failed: int
    skipped: int
    total: int
    pass_percentage: str
    total_duration: str
    serial_duration: str
    speedup: str
    passed_tests: list[Test] = field(default_factory=list[Test])
    failed_tests: list[Test] = field(default_factory=list[Test])
    failure_groups: list[FailureGroup] = field(default_factory=list[FailureGroup])


DESCRIPTION = (
    "Parse Robot Framework output.xml and write report to "
    "GitHub Actions step summary."
)


def parse_args(argv: list[str] | None = None) -> Args:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    _ = parser.add_argument(
        "--report_path",
        default=os.environ.get("REPORT_PATH", ""),
        help="Directory containing output.xml (default: $REPORT_PATH)",
    )
    _ = parser.add_argument(
        "--show_passed_tests",
        default=os.environ.get("SHOW_PASSED_TESTS", ""),
        help="Include passed tests in report if true (default: $SHOW_PASSED_TESTS)",
    )
    _ = parser.add_argument(
        "--failed_tests_on_top",
        default=os.environ.get("FAILED_TESTS_ON_TOP", ""),
        help="Show failed tests before passed tests if true (default: $FAILED_TESTS_ON_TOP)",
    )
    _ = parser.add_argument(
        "--report_type",
        default=os.environ.get("REPORT_TYPE", "full"),
        choices=["full", "compact", "minimal"],
        help="Report detail level: full, compact, or minimal (default: $REPORT_TYPE or full)",
    )
    _ = parser.add_argument(
        "--history_path",
        default=os.environ.get("HISTORY_PATH", ""),
        help="YAML file to append test result history (default: $HISTORY_PATH)",
    )
    _ = parser.add_argument(
        "--test_tags",
        default=os.environ.get("TEST_TAGS", ""),
        help="GitHub workflow input: test tags filter (default: $TEST_TAGS)",
    )
    _ = parser.add_argument(
        "--run_parallel",
        default=os.environ.get("RUN_PARALLEL", ""),
        help="GitHub workflow input: run in parallel if true (default: $RUN_PARALLEL)",
    )
    _ = parser.add_argument(
        "--thread_count",
        default=os.environ.get("THREAD_COUNT", ""),
        help="GitHub workflow input: parallel thread count (default: $THREAD_COUNT)",
    )
    _ = parser.add_argument(
        "--test_path",
        default=os.environ.get("TEST_PATH", ""),
        help="GitHub workflow input: test path filter (default: $TEST_PATH)",
    )
    raw = parser.parse_args(argv)
    return Args(
        report_path=cast(str, raw.report_path),
        show_passed_tests=cast(str, raw.show_passed_tests),
        failed_tests_on_top=cast(str, raw.failed_tests_on_top),
        report_type=cast(str, raw.report_type),
        history_path=cast(str, raw.history_path),
        test_tags=cast(str, raw.test_tags),
        run_parallel=cast(str, raw.run_parallel),
        thread_count=cast(str, raw.thread_count),
        test_path=cast(str, raw.test_path),
    )


def validate_args(args: Args) -> None:
    if not args.report_path:
        sys.exit("Report path missing. Please define REPORT_PATH environment variable.")


def parse_output_xml(report_path: str) -> Report:
    xml_path = os.path.join(report_path, "output.xml")
    if not os.path.isfile(xml_path):
        sys.exit(f"output.xml not found at {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    passed_tests: list[Test] = list()
    failed_tests: list[Test] = list()
    serial_duration: float = 0.0
    test_suite_paths: list[list[str]] = []
    test_map: dict[str, ET.Element] = {}

    parent_map: dict[ET.Element, ET.Element] = {}
    for p_elem in root.iter():
        for c_elem in p_elem:
            parent_map[c_elem] = p_elem

    for suite_elem in root.iter("suite"):
        for test_elem in suite_elem.findall("test"):
            name = test_elem.get("name", "")
            status_elem = test_elem.find("status")
            if status_elem is None:
                continue

            tags: list[str] = []
            test_id = ""
            for tag_elem in test_elem.iterfind("tag"):
                tag_text = (tag_elem.text or "").strip()
                if tag_text.startswith("id-"):
                    test_id = tag_text
                elif not tag_text.startswith("robot:"):
                    tags.append(tag_text)

            status = status_elem.get("status", "UNKNOWN")
            elapsed = status_elem.get("elapsed", "0")

            message = status_elem.text or ""
            message = message.replace("\n", " ").replace("|", "\\|").strip()

            try:
                execution_time = float(elapsed)
            except (ValueError, TypeError):
                log.warning("Invalid elapsed time '%s' for test '%s'", elapsed, name)
                execution_time = 0.0

            serial_duration += execution_time

            parts: list[str] = []
            node = parent_map.get(test_elem)
            while node is not None:
                if node.tag == "suite":
                    parts.append(node.get("name", "?"))
                node = parent_map.get(node)
            parts.reverse()
            test_suite_paths.append(parts)

            test: Test = Test(
                test_id=test_id,
                name=name,
                status=status,
                suite="/".join(parts),
                execution_time=execution_time,
                message=message,
                tags=", ".join(tags),
            )

            if status == "PASS":
                passed_tests.append(test)
            elif status == "FAIL":
                failed_tests.append(test)
                test_map[name] = test_elem

    if test_suite_paths:
        common_prefix = list(test_suite_paths[0])
        for path in test_suite_paths[1:]:
            i = 0
            while (
                i < len(common_prefix) and i < len(path) and common_prefix[i] == path[i]
            ):
                i += 1
            common_prefix = common_prefix[:i]
            if not common_prefix:
                break
        prefix_len = len(common_prefix)
    else:
        prefix_len = 0

    for test_list in (passed_tests, failed_tests):
        for test in test_list:
            parts = test.suite.split("/")
            trimmed = parts[prefix_len:]
            test.suite = "/".join(trimmed) if trimmed else test.suite

    passed_tests.sort(key=_sort_key)
    failed_tests.sort(key=_sort_key)

    suite_status = root.find("suite/status")
    if suite_status is None:
        sys.exit("Could not find suite status in output.xml")
    total_elapsed = float(suite_status.get("elapsed", "0"))

    stat_elem = root.find(".//statistics/total/stat")
    if stat_elem is None:
        sys.exit("Could not find statistics in output.xml")

    passed = int(stat_elem.get("pass", "0"))
    failed = int(stat_elem.get("fail", "0"))
    skipped = int(stat_elem.get("skip", "0"))

    if serial_duration > 0 and total_elapsed > 0:
        speedup = serial_duration / total_elapsed
        if speedup >= 1.05:
            speedup_str = f"{speedup:.1f}x faster"
        else:
            speedup_str = "—"
    else:
        speedup_str = "—"

    failure_groups = group_failures(failed_tests, test_map, parent_map)

    return Report(
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=passed + failed + skipped,
        pass_percentage=pass_percentage(passed, failed),
        total_duration=format_duration(total_elapsed),
        serial_duration=format_duration(serial_duration),
        speedup=speedup_str,
        passed_tests=passed_tests,
        failed_tests=failed_tests,
        failure_groups=failure_groups,
    )


def find_deepest_failure(
    test_elem: ET.Element, parent_map: dict[ET.Element, ET.Element]
) -> tuple[str, str]:
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


def _sort_key(t: Test) -> int:
    try:
        return int(t.test_id.split("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def pass_percentage(passed: int, failed: int) -> str:
    if passed > 0 and failed == 0:
        return "100"
    if passed <= 0:
        return "0"
    return f"{(passed / (passed + failed) * 100):.2f}"


def format_duration(total_seconds: float) -> str:
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds:.3f}s")
    return "".join(parts)


def message_cell(value: str) -> Markup:
    if not value:
        return Markup("")
    return Markup(f"<details><summary>show</summary>{html.escape(value)}</details>")


def write_history(report: Report, args: Args) -> None:
    if not args.history_path:
        return

    history: list[dict] = []
    if os.path.isfile(args.history_path):
        try:
            with open(args.history_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            if isinstance(loaded, list):
                history = loaded
        except yaml.YAMLError:
            log.warning("Failed to parse %s, starting fresh", args.history_path)

    try:
        thread_count = int(args.thread_count)
    except (ValueError, TypeError):
        thread_count = 0

    record = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "passed": report.passed,
        "failed": report.failed,
        "skipped": report.skipped,
        "total": report.total,
        "pass_percentage": report.pass_percentage,
        "total_duration": report.total_duration,
        "test_tags": args.test_tags,
        "run_parallel": args.run_parallel == "true",
        "thread_count": thread_count,
        "test_path": args.test_path,
    }
    history.append(record)

    with open(args.history_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(history, f, allow_unicode=True, sort_keys=False)

    log.info("Appended history record to %s", args.history_path)


def render_report(report: Report, args: Args) -> str:
    env: Environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        keep_trailing_newline=True,
    )
    env.filters["message_cell"] = message_cell  # type: ignore[unknown-member]
    template = env.get_template("report.jinja")
    return template.render(
        passed=report.passed,
        failed=report.failed,
        skipped=report.skipped,
        total=report.total,
        pass_percentage=report.pass_percentage,
        total_duration=report.total_duration,
        serial_duration=report.serial_duration,
        speedup=report.speedup,
        passed_tests=report.passed_tests,
        failed_tests=report.failed_tests,
        show_passed_tests=args.show_passed_tests == "true",
        failed_tests_on_top=args.failed_tests_on_top == "true",
        speedup_visible=report.speedup != "—",
        failure_groups=report.failure_groups,
        report_type=args.report_type,
    )


def write_summary(body: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        log.info("GITHUB_STEP_SUMMARY not set, printing to stdout")
        print(body)
        return

    log.info("Writing report to GITHUB_STEP_SUMMARY")
    with open(summary_path, "a", encoding="utf-8") as f:
        _ = f.write(body)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = parse_args(argv)
    validate_args(args)

    report = parse_output_xml(args.report_path)
    write_history(report, args)
    body = render_report(report, args)

    write_summary(body)


if __name__ == "__main__":
    main()
