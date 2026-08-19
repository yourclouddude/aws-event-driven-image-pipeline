# Contributing

Thanks for helping improve this YourCloudDude learner project.

## Before opening a pull request

1. keep the architecture focused on the problem being taught
2. avoid adding AWS services only to make the diagram more complex
3. update tests when behavior changes
4. keep IAM permissions as narrow as practical
5. document new failure modes, security implications, and cost implications
6. never commit credentials, account-specific secrets, or private data

Run the local checks:

```bash
ruff check .
python -m compileall src tests
pytest -q
sam validate --lint
sam build
```

A contribution should make the project more correct, maintainable, secure, or useful to learners. Formatting-only churn and unsupported claims should be avoided.
