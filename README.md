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
| `--history_path` | `HISTORY_PATH` | YAML file to append run-level stats to |
| `--track_path` | `TRACK_PATH` | YAML file for per-test aggregate stats, updated in place |
| `--test_tags` | `TEST_TAGS` | GitHub workflow input: test tags filter applied |
| `--run_parallel` | `RUN_PARALLEL` | GitHub workflow input: `true` if parallel run |
| `--thread_count` | `THREAD_COUNT` | GitHub workflow input: parallel thread count |
| `--test_path` | `TEST_PATH` | GitHub workflow input: test path filter applied |

### History Tracking

`--history_path` appends a run-level record each time (passed, failed,
skipped, total, pass %, duration, workflow inputs).  No per-test data —
that lives in the tracker file.

`--track_path` maintains a compact per-test tracker file.  Each run
reads it, produces the report columns, then updates it in place with the
current run's results.

Report columns (visible when `--track_path` is set):

- **Hist. Pass %** — cumulative pass rate from all prior runs
- **New Err?** — `Yes` if the test has never failed before
- **Consec. Fails** — failure streak including the current run

Example workflow step:

```yaml
- name: Generate report with tracking
  run: |
    robot-reporter \
      --report_path ./test-results \
      --history_path ./history.yml \
      --track_path ./tracker.yml \
      --test_tags "${{ inputs.test_tags }}" \
      --run_parallel "${{ inputs.run_parallel }}" \
      --thread_count "${{ inputs.thread_count }}" \
      --test_path "${{ inputs.test_path }}"
```

History YAML format (run-level only):

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
```

Tracker YAML format (per-test aggregates, updated in place):

```yaml
id-0001:
  passes: 10
  fails: 0
  consec_fails: 0
id-0002:
  passes: 2
  fails: 8
  consec_fails: 3
```
