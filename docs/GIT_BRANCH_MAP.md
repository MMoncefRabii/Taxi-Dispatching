# Git Branch Map

This document records the repository's branch and remote relationships so contributors can review them independently of the project overview. Update the current-ref section when branch names or upstreams change.

## Repository Layout

The project is a single Git repository rooted at `Taxi-Dispatching/`. `DriverApp/` is a regular directory in the root repository, not a Git submodule. This keeps a normal clone self-contained for local development and future CI pipelines. There is intentionally no `.gitmodules` file.

## Current Branches

Verified on 2026-10-02:

| Branch | Upstream | Role / state |
| --- | --- | --- |
| `main` | `origin/main` | Integration branch. The local branch contains the Fleet Tracker backend commit `e0f19b3`; the remote `main` currently points to `76b5a00`. |
| `feature/fleet-tracker-live-dashboard` | `origin/feature/fleet-tracker-live-dashboard` | Current working and published feature branch. Local and remote both point to `ac8acd3`. It contains the backend/dashboard work and the README/ignore updates. |

The mobile app changes are being consolidated into the root repository on the current feature branch. Do not rely on a separate `DriverApp` remote or branch; none is configured for this project.

## Suggested Branch Flow

1. Start feature work from an up-to-date `main` branch.
2. Use a descriptive branch name such as `feature/location-permissions` or `fix/driver-status-toggle`.
3. Push the feature branch to `origin` and open a pull request targeting `main`.
4. Run CI checks on pull requests and on updates to `main`; merge only after required checks pass.
5. Keep deployment credentials and environment-specific values in the CI secret store, not in Git.

The current feature branch name is retained for continuity. Future work can follow the suggested flow without changing existing history.

## Useful Checks

```powershell
git status --short --branch
git branch -vv
git remote -v
git log --oneline --decorate --graph -20
git fetch origin
git status --short --branch
```

`git fetch origin` refreshes local remote-tracking refs; it does not merge or rebase local work. Before pushing, inspect the branch and status, then push the current branch explicitly:

```powershell
git push -u origin <branch-name>
```