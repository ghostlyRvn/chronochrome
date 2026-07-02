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

TAG="v${NEW_VERSION}"
echo "==> Releasing ${TAG}"

echo "==> Running tests"
python3 -m pytest -q

echo "==> Committing and tagging"
git add "$INIT"
git commit -m "Release ${TAG}"
git tag "$TAG"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> Pushing ${BRANCH} and ${TAG}"
git push origin "$BRANCH"
git push origin "$TAG"

echo
echo "Done. CI will build the GitHub Release and bump the Homebrew tap for ${TAG}."
