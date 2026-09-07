# GitHub workflow for the project owner

This is the short, safe workflow for everyday IAAI development.

## Key terms

- **main**: the stable, protected branch.
- **branch**: an isolated line of work for one change.
- **commit**: a named snapshot of staged changes.
- **push**: upload local commits to GitHub.
- **pull**: download and integrate GitHub changes.
- **Pull Request (PR)**: a proposal to merge a branch into `main` after CI checks.
- **merge**: accept a Pull Request into `main`.
- **fork**: another user's GitHub copy of the repository.

## Normal workflow with Codex

1. Get the latest stable code:
   `git switch main` and then `git pull`.
2. Create a branch: `git switch -c feature/short-name`.
3. Ask Codex to make the focused change.
4. Run `ruff check .` and `pytest`.
5. Review the result with `git status` and `git diff`.
6. Stage intended files: `git add path/to/file` (or `git add .` after careful review).
7. Save the snapshot: `git commit -m "Describe the change"`.
8. Upload the branch: `git push -u origin feature/short-name`.
9. Open a Pull Request on GitHub and wait for CI to pass.
10. Merge the PR on GitHub, then update local `main` with `git switch main` and `git pull`.

Do not develop substantial changes directly on `main`. Never stage `.env`, secrets, datasets,
databases, model files, downloaded research sources, or local runtime output.
