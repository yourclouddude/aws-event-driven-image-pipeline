# Security Policy

## Reporting a vulnerability

Please do **not** open a public GitHub issue for a suspected security vulnerability.

If GitHub private vulnerability reporting is available for this repository, use **Security → Report a vulnerability**. Otherwise, contact YourCloudDude through https://yourclouddude.com/ with enough detail to reproduce and assess the issue safely.

Please include:

- the affected component or file
- a clear description of the vulnerability
- steps to reproduce it
- the potential impact
- any suggested mitigation, if you have one

Do not include real AWS credentials, access tokens, customer data, or other secrets in a report.

## Scope

This repository is a learning project, not a managed production service. Reports about unsafe upload handling, IAM boundaries, event processing, credential exposure, or infrastructure configuration are useful when they identify a concrete issue in the repository.

## Supported versions

Security fixes are applied to the current `main` branch. Older commits and forks are not maintained as separately supported releases.
