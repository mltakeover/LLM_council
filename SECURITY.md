# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private
vulnerability reporting on the Security tab, which notifies the maintainer
without disclosing the issue.

## Controls on contributions

This repository accepts pull requests from forks. Nothing merges to `master`
without passing the following:

| Control | What it catches |
|---|---|
| Branch protection | Direct pushes to `master`, unreviewed merges |
| CI (ruff, pytest, ESLint, build) | Broken or non-conforming code |
| CodeQL | Known vulnerability patterns in Python and JavaScript |
| Dependency review | New dependencies with known CVEs or denied licences |
| Secret scanning | Committed credentials |
| CODEOWNERS | Merges without maintainer approval |

## What these controls do not catch

Automated scanning finds *known patterns*. It does not reliably detect a
deliberate backdoor written to look ordinary. A malicious contribution is more
likely to arrive as a plausible bug fix that quietly widens a permission, or as
a new transitive dependency, than as obviously hostile code.

The controls that actually stop that are human: reading the diff, questioning
dependencies that were not needed before, and being suspicious of changes to
CI configuration, provider clients, or anything handling credentials.

## Notes for reviewers

When reviewing a pull request from an unknown contributor, look specifically at:

- **Workflow files.** A change to `.github/workflows/` can exfiltrate secrets
  or grant itself write access. Treat any such change as high risk.
- **New dependencies.** Check the package exists, is widely used, and is not a
  typo-squat of something popular. Dependency review reports known CVEs but
  cannot tell you a package is malicious.
- **Lockfile changes without manifest changes.** A modified
  `package-lock.json` or equivalent with no corresponding `package.json` change
  deserves an explanation.
- **Network calls and subprocess use.** New `httpx`, `requests`, `fetch`,
  `subprocess`, `eval` or `exec` calls in a change that had no reason to need
  them.
- **Base URL and credential handling.** Anything touching `backend/config.py`
  or `backend/providers.py`, where a redirected endpoint would send prompts and
  keys somewhere unintended.

## Workflow safety

CI uses the `pull_request` trigger, not `pull_request_target`. This matters:
`pull_request_target` runs with repository secrets and a write-capable token
against the contributor's code, and is the most commonly exploited Actions
misconfiguration. The workflows here have no access to secrets and a read-only
token.

Fork pull requests should require maintainer approval before workflows run.
This is a repository setting, under Settings → Actions → General → Fork pull
request workflows.
