#!/usr/bin/env bash
#
# One-command release.
#
#   scripts/release.sh patch      # 0.1.0 -> 0.1.1
#   scripts/release.sh minor      # 0.1.0 -> 0.2.0
#   scripts/release.sh major      # 0.1.0 -> 1.0.0
#   scripts/release.sh 1.4.2      # set an explicit version
#
# It bumps the single-source version in src/chronochrome/__init__.py, runs the
# tests, commits "Release vX.Y.Z", tags vX.Y.Z, and pushes. Pushing the tag
# triggers .github/workflows/release.yml, which builds the release AND bumps the
# Homebrew tap automatically — so this script is the only step you run by hand.
#
# Run it from your default branch with a clean working tree.

set -euo pipefail

cd "$(dirname "$0")/.."

BUMP="${1:-}"
if [[ -z "$BUMP" ]]; then
  echo "usage: scripts/release.sh <patch|minor|major|X.Y.Z>" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree is not clean. Commit or stash first." >&2
  exit 1
fi

INIT="src/chronochrome/__init__.py"

# If anything fails *before* we've committed, roll back the version bump so the
# working tree is left exactly as we found it. Once the release commit exists,
# the commit — not the working-tree edit — is the artifact, so we stop
# reverting: a failed tag/push just needs a re-run, not the version undone.
# VERSION_WRITTEN guards against clobbering a bump this script didn't make
# (e.g. a pre-existing dirty tree caught by the check above).
VERSION_WRITTEN=0
COMMITTED=0
rollback_on_failure() {
  local status=$?
  if [[ $status -ne 0 && $VERSION_WRITTEN -eq 1 && $COMMITTED -eq 0 ]]; then
    echo "==> Release failed (exit $status); reverting version bump in ${INIT}" >&2
    git checkout -- "$INIT"
  fi
}
trap rollback_on_failure EXIT

# Compute + write the new version (Python is guaranteed present in this project).
NEW_VERSION="$(python3 - "$BUMP" "$INIT" <<'PY'
import re, sys

bump, path = sys.argv[1], sys.argv[2]
with open(path) as fh:
    text = fh.read()

match = re.search(r'__version__ = "(\d+)\.(\d+)\.(\d+)"', text)
if not match:
    sys.exit(f"could not find __version__ in {path}")

major, minor, patch = (int(part) for part in match.groups())
if bump == "major":
    major, minor, patch = major + 1, 0, 0
elif bump == "minor":
    minor, patch = minor + 1, 0
elif bump == "patch":
    patch += 1
elif re.fullmatch(r"\d+\.\d+\.\d+", bump):
    major, minor, patch = (int(p) for p in bump.split("."))
else:
    sys.exit(f"invalid bump {bump!r}: use patch|minor|major or an explicit X.Y.Z")

new = f"{major}.{minor}.{patch}"
with open(path, "w") as fh:
    fh.write(text[: match.start()] + f'__version__ = "{new}"' + text[match.end():])
print(new)
PY
)"
VERSION_WRITTEN=1

TAG="v${NEW_VERSION}"
echo "==> Releasing ${TAG}"

echo "==> Running tests"
# Run via `uv run` so the dev deps (pytest) resolve from the project's
# environment regardless of whether a venv is activated in the caller's shell.
uv run pytest -q

echo "==> Committing and tagging"
git add "$INIT"
git commit -m "Release ${TAG}"
COMMITTED=1
git tag "$TAG"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> Pushing ${BRANCH} and ${TAG}"
git push origin "$BRANCH"
git push origin "$TAG"

echo
echo "Done. CI will build the GitHub Release and bump the Homebrew tap for ${TAG}."
