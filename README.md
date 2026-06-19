## Robot Reporter

Parse Robot Framework `output.xml` and write test results to the
GitHub Actions step summary. Intended to run as a workflow step with zero
setup.

### Usage

```bash
uv run robot-reporter --report_path ./test-results
```

The report is appended to `GITHUB_STEP_SUMMARY`, which renders automatically
on the workflow run page.

| Argument | Environment Variable | Description |
|---|---|---|
| `--report_path` | `REPORT_PATH` | Directory containing `output.xml` |
| `--summary` | `SUMMARY` | Write to step summary if `true` (defaults to `true`) |
| `--show_passed_tests` | `SHOW_PASSED_TESTS` | Include passed tests in report |
| `--failed_tests_on_top` | `FAILED_TESTS_ON_TOP` | Show failed tests before passed |
