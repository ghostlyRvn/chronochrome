# Releasing Chronochrome

Releasing is one command:

```sh
scripts/release.sh patch     # bug fixes            0.1.0 -> 0.1.1
scripts/release.sh minor     # new features         0.1.0 -> 0.2.0
scripts/release.sh major     # breaking changes     0.1.0 -> 1.0.0
scripts/release.sh 1.4.2     # or an explicit version
```

Run it from your default branch with a clean working tree.

## What that does

1. Bumps the version in `src/chronochrome/__init__.py` — the **single source of
   truth**. `pyproject.toml` reads it dynamically (`[tool.hatch.version]`) and
   `chronochrome --version` reads the same attribute, so nothing can drift.
2. Runs the test suite (aborts the release if it fails).
3. Commits `Release vX.Y.Z`, tags `vX.Y.Z`, and pushes the branch + tag.

Pushing the tag triggers [`.github/workflows/release.yml`](.github/workflows/release.yml),
which runs on its own with no further input from you:

4. Builds the sdist + wheel and re-runs the tests against the built artifact.
5. Publishes a **GitHub Release** with those artifacts and auto-generated notes.
6. Recomputes the source-tarball `sha256` and pushes the updated
   `Formula/chronochrome.rb` to the Homebrew tap
   (`ghostlyrvn/homebrew-chronochrome`).

So a normal release is: **run one command, done.** No files to hand-edit, no
formula to update, no checksum to copy.

## Versioning

Follow [SemVer](https://semver.org/): patch for fixes, minor for additive
features (e.g. a new editor adapter), major once the config schema / CLI is
something you promise to keep stable. Never re-tag an existing version — cut a
new one; users and Homebrew pin to the tag.

## First-time setup

The automatic tap bump needs a one-time setup (create the tap repo + a
`TAP_GITHUB_TOKEN` secret). See
[`packaging/homebrew/HOMEBREW.md`](packaging/homebrew/HOMEBREW.md). Until it's
configured, steps 1–5 still work; only the tap bump (step 6) is skipped.

## Not yet wired: PyPI

The workflow attaches the wheel/sdist to the GitHub Release but does not upload
to PyPI, so `pipx install chronochrome` (bare name) doesn't work yet — only
`pipx install git+https://github.com/ghostlyrvn/chronochrome`. Adding PyPI
trusted publishing to the release workflow is a small follow-up if you want the
bare-name install.
