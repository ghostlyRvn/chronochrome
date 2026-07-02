# Publishing Chronochrome via Homebrew

Chronochrome has **zero runtime dependencies** (stdlib only), so its formula is
about as simple as a Python formula gets — no `resource` blocks to vendor. The
work is release plumbing, not the formula.

The canonical formula lives at
[`packaging/homebrew/chronochrome.rb`](./chronochrome.rb) in this repo. It seeds
the tap once; after that, CI keeps the tap's copy up to date automatically —
see [`../../RELEASING.md`](../../RELEASING.md) for the day-to-day release flow.

---

## One-time setup

Do these three things once. After that, releasing is a single command
(`scripts/release.sh patch`) and the tap updates itself.

### 1. Create the tap

A "tap" is just a GitHub repo whose name starts with `homebrew-`.

1. Create a public repo named **`ghostlyrvn/homebrew-chronochrome`**.
2. Seed it with the formula at `Formula/chronochrome.rb` (copy from this repo)
   and fill in the real `sha256` for the current tag:
   ```sh
   mkdir -p Formula
   cp /path/to/chronochrome/packaging/homebrew/chronochrome.rb Formula/chronochrome.rb
   curl -sL https://github.com/ghostlyrvn/chronochrome/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256
   # paste that sha256 into Formula/chronochrome.rb, then:
   git add Formula/chronochrome.rb && git commit -m "chronochrome 0.1.0" && git push
   ```

Users then install with:

```sh
brew install ghostlyrvn/chronochrome/chronochrome
# or, tap first:
brew tap ghostlyrvn/chronochrome && brew install chronochrome
```

### 2. Create a tap-write token

The release workflow needs to push the updated formula to the *other* repo
(the tap), which the default `GITHUB_TOKEN` can't do.

1. Create a **fine-grained PAT** scoped to `ghostlyrvn/homebrew-chronochrome`
   with **Contents: Read and write**.
2. In **this** repo's settings → Secrets and variables → Actions, add it as
   **`TAP_GITHUB_TOKEN`**.

Until this secret exists the `bump-homebrew-tap` job simply no-ops (the GitHub
Release still publishes), so nothing breaks before you set it up.

### 3. That's it

From now on, `scripts/release.sh <patch|minor|major>` is the whole release.

---

## Verify the formula before you publish

From a checkout of the tap (or pointing at the local file):

```sh
brew install --build-from-source ./Formula/chronochrome.rb
brew test chronochrome
brew audit --strict --online chronochrome
brew style chronochrome
```

All four should pass. `audit` and `style` are required for homebrew-core and
are good hygiene for a tap too.

---

## Notes / decisions

- **Python version:** the formula pins `depends_on "python@3.12"`. The project
  supports 3.11+, but Homebrew formulae depend on a specific `python@X.Y`
  keg. Bump this line when Homebrew's default Python moves forward.

- **Scheduler ownership:** `chronochrome install` writes its own launchd/systemd
  unit, and that stays the source of truth on the Homebrew path too — so the
  experience is identical across `pipx`, `uv tool`, and `brew`. We deliberately
  do **not** add a Homebrew `service do ... end` block, to avoid two competing
  ways to register the job (and because the interval lives in `config.toml`,
  not the formula). After `brew install`, users still run `chronochrome install`
  to register the timer.

- **Bottles:** the formula builds from source. If installs get slow enough to
  care, add a `brew test-bot`-based bottling workflow to the tap so users get
  prebuilt binaries. Not needed at this scale.

- **homebrew-core:** submitting to core (so `brew install chronochrome` works
  with no tap prefix) requires meeting Homebrew's notability bar (a project
  that's already widely used). Revisit once the project has traction; the tap
  is the right home until then.
