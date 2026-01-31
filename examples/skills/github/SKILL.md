---
name: github
description: "Interact with GitHub repositories, issues, and pull requests using the gh CLI"
metadata:
  emoji: "🐙"
  homepage: "https://cli.github.com"
  requires:
    bins:
      - gh
    env:
      - GITHUB_TOKEN
  primary_env: "GITHUB_TOKEN"
  install:
    - kind: brew
      id: gh
      label: "GitHub CLI (Homebrew)"
      bins: ["gh"]
      os: ["darwin", "linux"]
user-invocable: true
---

# GitHub CLI Skill

Use the `gh` CLI to interact with GitHub. Available commands:

## Repository Operations
- `gh repo list` - List your repositories
- `gh repo view [repo]` - View repository details
- `gh repo clone [repo]` - Clone a repository

## Issues
- `gh issue list` - List issues
- `gh issue create` - Create a new issue
- `gh issue view [number]` - View issue details

## Pull Requests
- `gh pr list` - List pull requests
- `gh pr create` - Create a pull request
- `gh pr view [number]` - View PR details
- `gh pr checkout [number]` - Check out a PR locally
- `gh pr merge [number]` - Merge a pull request

## Workflow
- `gh run list` - List workflow runs
- `gh run view [run-id]` - View run details
- `gh run watch [run-id]` - Watch a run

Always check `gh --help` for more commands and options.
