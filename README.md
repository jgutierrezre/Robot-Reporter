## Robot Reporter

Parse Robot Framework `output.xml` and post test results as a GitHub comment
on a PR or commit. Also writes to the GitHub Actions step summary when run in a
workflow.

### Usage

```bash
uv run robot-reporter \
  --report_path ./test-results \
  --repo_owner myorg \
  --repository myrepo \
  --commit_sha "$COMMIT_SHA" \
  --access_token "$GH_ACCESS_TOKEN"
```

For a pull request:

```bash
uv run robot-reporter \
  --report_path ./test-results \
  --repo_owner myorg \
  --repository myrepo \
  --pull_request_id "$PR_ID" \
  --access_token "$GH_ACCESS_TOKEN"
```

All arguments also read from environment variables:

| Argument | Environment Variable | Description |
|---|---|---|
| `--access_token` | `GH_ACCESS_TOKEN` | GitHub access token |
| `--repo_owner` | `REPO_OWNER` | Repository owner |
| `--repository` | `REPOSITORY` | Repository name |
| `--commit_sha` | `COMMIT_SHA` | Commit SHA |
| `--report_path` | `REPORT_PATH` | Directory containing `output.xml` |
| `--pull_request_id` | `PR_ID` | PR number |
| `--summary` | `SUMMARY` | Also write to GITHUB_STEP_SUMMARY |
| `--only_summary` | `ONLY_SUMMARY` | Only write summary, skip comment |
| `--show_passed_tests` | `SHOW_PASSED_TESTS` | Include passed tests in report |
| `--failed_tests_on_top` | `FAILED_TESTS_ON_TOP` | Show failed tests before passed |
