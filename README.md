## Robot Reporter

Parse Robot Framework `output.xml` and write test results to the
GitHub Actions step summary.

### Usage

```bash
uv run robot-reporter --report_path ./test-results
```

The report is appended to `GITHUB_STEP_SUMMARY`.

### Arguments

| Argument | Environment Variable | Description |
|---|---|---|
| `--report_path` | `REPORT_PATH` | Directory containing `output.xml` |
| `--show_passed_tests` | `SHOW_PASSED_TESTS` | Include passed tests in report (`true` to enable) |
| `--failed_tests_on_top` | `FAILED_TESTS_ON_TOP` | Show failed tests before passed (`true` to enable) |
| `--report_type` | `REPORT_TYPE` | Report detail: `full`, `compact`, `minimal` (default: `full`) |
| `--history_path` | `HISTORY_PATH` | YAML file to persist test history across runs |
| `--test_tags` | `TEST_TAGS` | GitHub workflow input: test tags filter applied |
| `--run_parallel` | `RUN_PARALLEL` | GitHub workflow input: `true` if parallel run |
| `--thread_count` | `THREAD_COUNT` | GitHub workflow input: parallel thread count |
| `--test_path` | `TEST_PATH` | GitHub workflow input: test path filter applied |

### History Tracking

When `--history_path` is set, each run appends a record to the YAML file
containing the results table (passed, failed, skipped, total, pass %,
duration) plus per-test outcomes and workflow inputs.

On subsequent runs, the report augments each test with:

- **Hist. Pass %** — historical pass rate across all prior runs
- **New?** — shows `Yes` if the test has never been seen in history

Example workflow step:

```yaml
- name: Generate report with history
  run: |
    robot-reporter \
      --report_path ./test-results \
      --history_path ./test-history.yml \
      --test_tags "${{ inputs.test_tags }}" \
      --run_parallel "${{ inputs.run_parallel }}" \
      --thread_count "${{ inputs.thread_count }}" \
      --test_path "${{ inputs.test_path }}"
```

History YAML format:

```yaml
- timestamp: '2026-07-02 14:30:00'
  passed: 161
  failed: 16
  skipped: 0
  total: 177
  pass_percentage: '90.96'
  total_duration: 19m23.421s
  test_tags: smoke
  run_parallel: true
  thread_count: 4
  test_path: Tests
  tests:
    - test_id: id-0001
      status: PASS
    - test_id: id-0002
      status: FAIL
```
