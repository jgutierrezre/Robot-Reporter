#!/usr/bin/env python3
"""Robot Reporter - Parse Robot Framework output.xml and post results to GitHub step summary."""

import argparse
import logging
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import cast

from jinja2 import Environment, FileSystemLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "templates")

log = logging.getLogger(__name__)


@dataclass
class Args:
    report_path: str
    summary: str
    show_passed_tests: str
    failed_tests_on_top: str


@dataclass
class Test:
    name: str
    status: str
    suite: str
    execution_time: float
    message: str


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
    passed_tests: list[Test] = field(default_factory=list)
    failed_tests: list[Test] = field(default_factory=list)
    show_passed_tests: bool = False
    failed_tests_on_top: bool = False


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
        "--summary",
        default=os.environ.get("SUMMARY", ""),
        help="Write report to GitHub step summary if true (default: $SUMMARY)",
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
    raw = parser.parse_args(argv)
    return Args(
        report_path=cast(str, raw.report_path),
        summary=cast(str, raw.summary),
        show_passed_tests=cast(str, raw.show_passed_tests),
        failed_tests_on_top=cast(str, raw.failed_tests_on_top),
    )


def validate_args(args: Args) -> None:
    if not args.report_path:
        sys.exit(
            "Report path missing. Please define REPORT_PATH environment variable."
        )


def parse_output_xml(report_path: str) -> Report:
    xml_path = os.path.join(report_path, "output.xml")
    if not os.path.isfile(xml_path):
        sys.exit(f"output.xml not found at {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    passed_tests: list[Test] = []
    failed_tests: list[Test] = []
    serial_duration = 0.0

    for suite_elem in root.iter("suite"):
        suite_name = suite_elem.get("name", "Unknown Suite")
        for test_elem in suite_elem.iter("test"):
            name = test_elem.get("name", "")
            status_elem = test_elem.find("status")
            if status_elem is None:
                continue

            status = status_elem.get("status", "UNKNOWN")
            elapsed = status_elem.get("elapsed", "0")

            message = status_elem.text or ""
            message = message.replace("\n", " ").strip()

            try:
                execution_time = float(elapsed)
            except (ValueError, TypeError):
                log.warning(
                    "Invalid elapsed time '%s' for test '%s'", elapsed, name
                )
                execution_time = 0.0

            serial_duration += execution_time

            test = Test(
                name=name,
                status=status,
                suite=suite_name,
                execution_time=execution_time,
                message=message,
            )

            if status == "PASS":
                passed_tests.append(test)
            elif status == "FAIL":
                failed_tests.append(test)

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
    )


def pass_percentage(passed: int, failed: int) -> str:
    if passed > 0 and failed == 0:
        return "100"
    if passed > 0 and failed > 0:
        return f"{(passed / (passed + failed) * 100):.2f}"
    return "0"


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


def render_report(report: Report, args: Args) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=False,
        keep_trailing_newline=True,
    )
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
    )


def write_summary(body: str, args: Args) -> None:
    if args.summary != "true":
        return

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        log.warning("GITHUB_STEP_SUMMARY not set, skipping summary write")
        return

    log.info("Writing report to GITHUB_STEP_SUMMARY")
    with open(summary_path, "a", encoding="utf-8") as f:
        _ = f.write(body)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = parse_args(argv)
    validate_args(args)

    report = parse_output_xml(args.report_path)
    body = render_report(report, args)

    if output := os.environ.get("GITHUB_OUTPUT"):
        log.info("Writing report_body to GITHUB_OUTPUT")
        with open(output, "a", encoding="utf-8") as f:
            _ = f.write(f"report_body<<EOF\n{body}\nEOF\n")

    write_summary(body, args)


if __name__ == "__main__":
    main()
