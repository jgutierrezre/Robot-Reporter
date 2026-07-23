## Architecture

```
reporter.py          Main script: parses XML, computes history, renders template
templates/
  report.jinja       Jinja2 template for the GitHub step summary markdown
grouping.py           Opt-in failure grouping (disabled by default)
```

---

## `reporter.py` — Main Script

### Dataclasses

**`Args`** — CLI argument bag (rendered from `argparse`)

| Field | Type | Source |
|---|---|---|
| `report_path` | `str` | `--report_path` / `$REPORT_PATH` |
| `show_passed_tests` | `str` | `--show_passed_tests` / `$SHOW_PASSED_TESTS` |
| `failed_tests_on_top` | `str` | `--failed_tests_on_top` / `$FAILED_TESTS_ON_TOP` |
| `report_type` | `str` | `--report_type` / `$REPORT_TYPE` (`full`/`compact`/`minimal`) |
| `history_path` | `str` | `--history_path` / `$HISTORY_PATH` |
| `test_tags` | `str` | `--test_tags` / `$TEST_TAGS` |
| `run_parallel` | `str` | `--run_parallel` / `$RUN_PARALLEL` (`"true"` or `""`) |
| `thread_count` | `str` | `--thread_count` / `$THREAD_COUNT` |
| `test_path` | `str` | `--test_path` / `$TEST_PATH` |

All fields are raw strings; `run_parallel` and `thread_count` are coerced to
`bool` / `int` at point of use.

---

**`Test`** — A single Robot Framework test case result.

| Field | Type | Source |
|---|---|---|
| `test_id` | `str` | `id-####` tag, or `""` |
| `name` | `str` | test `name` attribute |
| `status` | `str` | `"PASS"` or `"FAIL"` |
| `suite` | `str` | trimmed suite path (common prefix removed) |
| `execution_time` | `float` | elapsed seconds |
| `message` | `str` | failure message (newlines→spaces, pipes escaped) |
| `tags` | `str` | comma-separated non-`robot:` tags |

---

**`Report`** — Aggregated parse result.

| Field | Type |
|---|---|
| `passed` / `failed` / `skipped` / `total` | `int` |
| `pass_percentage` | `str` (e.g. `"90.96"`) |
| `total_duration` | `str` (e.g. `"19m23.421s"`) |
| `serial_duration` | `str` |
| `speedup` | `str` (e.g. `"7.7x faster"` or `"—"`) |
| `passed_tests` | `list[Test]` |
| `failed_tests` | `list[Test]` |

---

**`HistoryRecord`** — One run's worth of data written to the history YAML.

| Field | Type |
|---|---|
| `timestamp` | `str` (`"YYYY-MM-DD HH:MM:SS"`) |
| `passed` / `failed` / `skipped` / `total` | `int` |
| `pass_percentage` | `str` |
| `total_duration` | `str` |
| `test_tags` | `str` |
| `run_parallel` | `bool` |
| `thread_count` | `int` |
| `test_path` | `str` |
| `tests` | `list[dict[str,str]]` — the per-test `{test_id, status}` pairs |

Serialized to YAML via `asdict()`.

---

**`TestHistoryResult`** — Per-test summary derived from all prior history runs.

| Field | Type | Meaning |
|---|---|---|
| `pass_pct` | `str` | `"100%"`, `"0%"`, or `"—"` (no history) |
| `is_new_error` | `bool` | `True` when this test has **never failed** in any prior run |
| `consec_fails` | `int` | consecutive failures at the tail of the history (resets on `PASS`) |

---

### Functions

---

#### `parse_args(argv: list[str] | None = None) -> Args`

Builds an `argparse.ArgumentParser` with 9 flags.  Each flag's `default` is
read from a matching environment variable (e.g. `--report_path` reads
`$REPORT_PATH`).  Returns a populated `Args` dataclass.

---

#### `validate_args(args: Args) -> None`

Exits with a message if `args.report_path` is empty.

---

#### `parse_output_xml(report_path: str) -> Report`

1. Opens `<report_path>/output.xml` and builds a `parent_map` (element →
   parent) for tree traversal.
2. Iterates every `<test>` inside `<suite>` elements:
   - Extracts `name`, `status`, `elapsed`, failure `message`.
   - Collects tags: `id-####` → `test_id`; non-`robot:` tags → `tags`.
   - Walks the `parent_map` upward to assemble the suite path.
3. Sorts tests into `passed_tests` / `failed_tests`.
4. Trims the longest common suite-prefix from all tests.
5. Sorts both lists by numeric `id-####`.
6. Reads aggregate statistics from `<statistics/total/stat>` and suite-level
   elapsed time.
7. Computes speedup ratio (`serial_duration / total_elapsed`).
8. Returns a `Report`.

---

#### `id_sort_key(t: Test) -> int`

Extracts the numeric portion of `id-####` for stable sort ordering.

---

#### `pass_percentage(passed: int, failed: int) -> str`

Returns `"100"`, `"0"`, or `"NN.NN"` — pass rate ignoring skips.

---

#### `format_duration(total_seconds: float) -> str`

Converts seconds to a compact string: `"1h2m3.456s"`.

---

#### `message_cell(value: str) -> Markup`

Wraps a failure message in an HTML `<details><summary>show</summary>…`
element for the full report table.

---

#### `load_history(history_path: str) -> list[dict[str, object]]`

Reads the YAML file at `history_path` (if it exists and is valid).  Returns a
list of run records, or `[]` if missing / unparseable.  Each record is a dict
matching `HistoryRecord` shape.

---

#### `compute_test_history(history_entries: list[dict[str, object]]) -> dict[str, TestHistoryResult]`

Walks history records **in chronological order** (they are appended this way).
For each `test_id`:
- `pass` / `fail`: cumulative counts.
- `consec_fails`: increments on `FAIL`, resets to `0` on `PASS`.

From the final tallies:
- `pass_pct` → `"85%"` or `"—"` if never seen.
- `is_new_error` → `True` when `fail == 0` (error never occurred before).
- `consec_fails` → as computed.

Returns a dict keyed by `test_id`.

The template adds `+1` to `consec_fails` for tests that are **currently failing**
to include the current run in the streak.

---

#### `write_history(report: Report, args: Args) -> None`

No-op when `args.history_path` is empty.

1. Loads the existing history YAML (starts fresh on parse error).
2. Collects per-test `{test_id, status}` pairs from every test in the current
   `Report`.
3. Builds a `HistoryRecord` from `Report` + `Args` + per-test data.
4. Converts to dict via `asdict()` and appends to the list.
5. Writes the full list back to the YAML file.

---

#### `render_report(report: Report, args: Args, test_history: dict[str, TestHistoryResult]) -> str`

1. Creates a Jinja2 `Environment` with `FileSystemLoader` pointing to the
   `templates/` directory.
2. Registers the `message_cell` custom filter.
3. Loads `report.jinja` and renders it with the full context:
   - Aggregate counts, durations, speedup.
   - `passed_tests` / `failed_tests` lists.
   - `test_history` dict for per-test historical columns.
   - Boolean flags from `args`.
   - `report_type`.

---

#### `write_summary(body: str) -> None`

Appends the rendered markdown to `$GITHUB_STEP_SUMMARY` (if set), otherwise
prints to stdout.

---

#### `main(argv: list[str] | None = None) -> None`

Pipeline:

```
parse_args → validate_args → parse_output_xml
    → load_history → compute_test_history
    → write_history → render_report → write_summary
```

History is computed **before** the current run is written, so the current run's
tests do not self-reference.

---

## `grouping.py` — Opt-in Failure Grouping

Extracted from the main script so it can be brought back if needed.  Not called
in the default pipeline.

### Dataclass

**`FailureGroup`** — a cluster of failures sharing the same root cause.

| Field | Type |
|---|---|
| `failing_keyword` | `str` — deepest failing keyword name |
| `message_signature` | `str` — normalized message |
| `count` | `int` — number of failures in this group |
| `tests` | `list[Test]` — the individual test results |

### Functions

#### `find_deepest_failure(test_elem, parent_map) -> tuple[str, str]`

Walks the XML keyword tree depth-first.  Selects the deepest `<kw>` whose
status is `FAIL` and whose parent keyword (or `<test>`) is also failing.
Returns `(keyword_name, message)`.  Falls back to `("(test level)", …)` if no
failing keyword is found.

#### `normalize_message(message: str) -> str`

Produces a stable string for grouping:
- Strips stacktraces.
- Replaces locators (`css:…`, `xpath:…`, etc.) with `'LOCATOR'`.
- Replaces hex addresses with `0xN`.
- Replaces numbers with `N`.
- Collapses whitespace.

#### `group_failures(failed_tests, test_map, parent_map) -> list[FailureGroup]`

Clusters `failed_tests` by `(deepest_failing_keyword, normalized_message)`.
Returns groups sorted by count descending.

### Usage (manual)

```python
from grouping import group_failures

failure_groups = group_failures(report.failed_tests, test_map, parent_map)
```
