## What changed?

Describe the problem this PR solves and the approach you took.

## Why this approach?

Explain any S3, SQS, Lambda, retry, concurrency, IAM, or failure-handling trade-offs introduced by the change.

## Validation

- [ ] `ruff check .`
- [ ] `python -m compileall src tests`
- [ ] `pytest -q`
- [ ] `sam validate --lint`
- [ ] `sam build`
- [ ] No credentials, secrets, test uploads, or generated deployment artifacts were committed

## Risk / rollback

Describe failure modes, queue/DLQ implications, affected AWS resources, and how the change can be reverted or cleaned up.

## Documentation

- [ ] README/docs updated when behavior or architecture changed
- [ ] No documentation change needed
