#!/usr/bin/env python3
"""Robot Reporter - Parse Robot Framework output.xml and post results to GitHub."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import requests
from jinja2 import Environment, FileSystemLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "assets")

log = logging.getLogger(__name__)


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
    skipped: str
    total: int
    pass_percentage: str
    total_duration: str
    passed_tests: list[Test] = field(default_factory=list)
    failed_tests: list[Test] = field(default_factory=list)
    show_passed_tests: bool = False
    failed_tests_on_top: bool = False


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse Robot Framework output.xml and post results to GitHub.",
    )
    parser.add_argument(
        "--access_token",
        default=os.environ.get("GH_ACCESS_TOKEN", ""),
        help="GitHub Access Token (default: $GH_ACCESS_TOKEN)",
    )
    parser.add_argument(
        "--repo_owner",
        default=os.environ.get("REPO_OWNER", ""),
        help="Repository owner (default: $REPO_OWNER)",
    )
    parser.add_argument(
        "--sha",
        dest="commit_sha",
        default=os.environ.get("COMMIT_SHA", ""),
        help="Commit SHA (default: $COMMIT_SHA)",
    )
    parser.add_argument(
        "--repository",
        default=os.environ.get("REPOSITORY", ""),
        help="Repository name (default: $REPOSITORY)",
    )
    parser.add_argument(
        "--report_path",
        default=os.environ.get("REPORT_PATH", ""),
        help="Directory containing output.xml (default: $REPORT_PATH)",
    )
    parser.add_argument(
        "--pull_request_id",
        default=os.environ.get("PR_ID", ""),
        help="Pull request number (default: $PR_ID)",
    )
    parser.add_argument(
        "--summary",
        default=os.environ.get("SUMMARY", ""),
        help="Write report to GitHub step summary if true (default: $SUMMARY)",
    )
    parser.add_argument(
        "--only_summary",
        default=os.environ.get("ONLY_SUMMARY", ""),
        help="Only write to step summary, skip PR/commit comment (default: $ONLY_SUMMARY)",
    )
    parser.add_argument(
        "--show_passed_tests",
        default=os.environ.get("SHOW_PASSED_TESTS", ""),
        help="Include passed tests in report if true (default: $SHOW_PASSED_TESTS)",
    )
    parser.add_argument(
        "--failed_tests_on_top",
        default=os.environ.get("FAILED_TESTS_ON_TOP", ""),
        help="Show failed tests before passed tests if true (default: $FAILED_TESTS_ON_TOP)",
    )
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.only_summary == "true" and args.summary != "true":
        args.summary = "true"

    if args.only_summary != "true":
        if not args.access_token:
            sys.exit(
                "Token missing. Please define GH_ACCESS_TOKEN environment variable."
            )
        if not args.repo_owner:
            sys.exit(
                "Owner missing. Please define REPO_OWNER environment variable."
            )
        if not args.commit_sha and not args.pull_request_id:
            sys.exit(
                "Either SHA or PR ID needs to be defined. "
                "Please define COMMIT_SHA or PR_ID environment variable."
            )
        if not args.repository:
            sys.exit(
                "Repository missing. Please define REPOSITORY environment variable."
            )

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
    total_duration = 0.0

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
                log.warning("Invalid elapsed time '%s' for test '%s'", elapsed, name)
                execution_time = 0.0

            total_duration += execution_time

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

    stat_elem = root.find(".//statistics/total/stat")
    if stat_elem is None:
        sys.exit("Could not find statistics in output.xml")

    passed = int(stat_elem.get("pass", "0"))
    failed = int(stat_elem.get("fail", "0"))
    skipped = stat_elem.get("skip", "0")

    return Report(
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=passed + failed,
        pass_percentage=pass_percentage(passed, failed),
        total_duration=format_duration(total_duration),
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
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds:.3f}s")
    return "".join(parts)


def render_report(report: Report, args: argparse.Namespace) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template("template.md")
    return template.render(
        passed=report.passed,
        failed=report.failed,
        skipped=report.skipped,
        total=report.total,
        pass_percentage=report.pass_percentage,
        total_duration=report.total_duration,
        passed_tests=report.passed_tests,
        failed_tests=report.failed_tests,
        show_passed_tests=args.show_passed_tests == "true",
        failed_tests_on_top=args.failed_tests_on_top == "true",
        failed_tests_count=len(report.failed_tests),
        passed_tests_count=len(report.passed_tests),
    )


def get_api_base() -> str:
    return os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")


def post_report(token: str, args: argparse.Namespace, body: str) -> None:
    if args.only_summary == "true":
        return

    api_base = get_api_base()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "robot-reporter",
    }

    if args.pull_request_id:
        post_to_pr(api_base, headers, args, body)
    else:
        post_to_commit(api_base, headers, args, body)


def post_to_pr(
    api_base: str,
    headers: dict[str, str],
    args: argparse.Namespace,
    body: str,
) -> None:
    pr_id = int(args.pull_request_id)
    comments_url = (
        f"{api_base}/repos/{args.repo_owner}/{args.repository}"
        f"/issues/{pr_id}/comments"
    )

    resp = requests.get(comments_url, headers=headers, timeout=30)
    resp.raise_for_status()
    comments = resp.json()

    for comment in comments:
        if comment.get("body", "").strip().startswith("### Robot Results"):
            comment_id = comment["id"]
            update_url = (
                f"{api_base}/repos/{args.repo_owner}/{args.repository}"
                f"/issues/comments/{comment_id}"
            )
            resp = requests.patch(
                update_url, headers=headers, json={"body": body}, timeout=30
            )
            resp.raise_for_status()
            log.info("Updated existing PR comment %d on #%d", comment_id, pr_id)
            return

    resp = requests.post(
        comments_url, headers=headers, json={"body": body}, timeout=30
    )
    resp.raise_for_status()
    log.info("Created new PR comment on #%d", pr_id)


def post_to_commit(
    api_base: str,
    headers: dict[str, str],
    args: argparse.Namespace,
    body: str,
) -> None:
    commit_url = (
        f"{api_base}/repos/{args.repo_owner}/{args.repository}"
        f"/commits/{args.commit_sha}/comments"
    )
    resp = requests.post(
        commit_url, headers=headers, json={"body": body}, timeout=30
    )
    resp.raise_for_status()
    log.info("Created commit comment on %s", args.commit_sha)


def write_summary(body: str, args: argparse.Namespace) -> None:
    if args.summary != "true":
        return

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        log.warning("GITHUB_STEP_SUMMARY not set, skipping summary write")
        return

    log.info("Writing report to GITHUB_STEP_SUMMARY")
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(body)


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = parse_args(argv)
    validate_args(args)

    report = parse_output_xml(args.report_path)
    body = render_report(report, args)

    post_report(args.access_token, args, body)
    write_summary(body, args)


if __name__ == "__main__":
    main()
