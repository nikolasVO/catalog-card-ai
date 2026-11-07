#!/usr/bin/env bash
# Create a public GitHub repository from this working directory using GitHub CLI.
# Run after `gh auth login`. Rejects private .env files, including Git history.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
REPO="${1:-catalog-card-ai}"
if [[ ! "$REPO" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)?$ ]]; then
  echo "Use a repository name or OWNER/NAME." >&2
  exit 2
fi
if ! command -v git >/dev/null 2>&1; then
  echo "Git is required." >&2
  exit 2
fi

private_env_paths_present() {
  local path filename
  while IFS= read -r -d '' path; do
    filename="${path##*/}"
    case "$filename" in
      .env.example) ;;
      .env|.env.*)
        printf 'Private environment file: %s\n' "$path" >&2
        return 0
        ;;
    esac
  done
  return 1
}

# Read-only preflight comes before staging, committing or renaming a branch.
IN_REPO=false
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IN_REPO=true
  if [[ "$(git rev-parse --show-toplevel)" != "$PROJECT_ROOT" ]]; then
    echo "Refusing to publish a directory inside another repository." >&2
    exit 3
  fi
  if git remote get-url origin >/dev/null 2>&1; then
    echo "origin is already configured; use your existing GitHub workflow." >&2
    exit 3
  fi
  if private_env_paths_present < <(git ls-files --cached -z); then
    echo "Refusing to publish: a private .env file is tracked or staged." >&2
    exit 3
  fi
  if [[ -n "$(git for-each-ref --format='%(refname)')" ]] && \
      private_env_paths_present < <(git log --all --format= --name-only --diff-filter=ACMR -z); then
    echo "Refusing to publish: Git history contains a private .env file." >&2
    exit 3
  fi
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required: https://cli.github.com/" >&2
  exit 2
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "Log in to GitHub first: gh auth login" >&2
  exit 2
fi
if [[ "$IN_REPO" == false ]]; then
  git init
fi
if [[ -f .env ]] && ! git check-ignore -q --no-index .env; then
  echo "Refusing to publish: the local .env is not ignored by Git." >&2
  exit 3
fi
git add .
if private_env_paths_present < <(git ls-files --cached -z); then
  echo "Refusing to publish: a private .env file is staged." >&2
  exit 3
fi
if [[ -n "$(git status --porcelain)" ]]; then
  GH_LOGIN="$(gh api user --jq .login)"
  GH_ID="$(gh api user --jq .id)"
  AUTHOR_NAME="${GIT_AUTHOR_NAME:-$(git config user.name || printf '%s' "$GH_LOGIN")}"
  AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-$(git config user.email || printf '%s+%s@users.noreply.github.com' "$GH_ID" "$GH_LOGIN")}"
  git -c user.name="$AUTHOR_NAME" -c user.email="$AUTHOR_EMAIL" \
      commit -m "Build AI product card drafting MVP"
fi
git branch -M main
# Does not overwrite existing repositories or force-push.
gh repo create "$REPO" --public --source=. --remote=origin --push
printf '\nRepository: '
gh repo view --json url -q .url
