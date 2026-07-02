# Publishing Chronochrome via Homebrew

Chronochrome has **zero runtime dependencies** (stdlib only), so its formula is
about as simple as a Python formula gets — no `resource` blocks to vendor. The
work is release plumbing, not the formula.

The canonical formula lives at
[`packaging/homebrew/chronochrome.rb`](./chronochrome.rb) in this repo; the tap
repo holds a copy. Keep them in sync when you cut a release.

---

## One-time setup: create the tap

A "tap" is just a GitHub repo whose name starts with `homebrew-`.

1. Create a public repo named **`ghostlyrvn/homebrew-chronochrome`**.
2. Add the formula at `Formula/chronochrome.rb` (copy from this repo):
   ```sh
   mkdir -p Formula
   cp /path/to/chronochrome/packaging/homebrew/chronochrome.rb Formula/chronochrome.rb
   git add Formula/chronochrome.rb && git commit -m "chronochrome 0.1.0" && git push
   ```

Users then install with:

```sh
brew install ghostlyrvn/chronochrome/chronochrome
# or, tap first:
brew tap ghostlyrvn/chronochrome && brew install chronochrome
```

---

## Each release

1. **Bump the version** in `pyproject.toml` (and `src/chronochrome/__init__.py`).
2. **Tag and push** — this triggers `.github/workflows/release.yml`:
   ```sh
   git tag v0.1.0 && git push origin v0.1.0
   ```
3. The workflow builds the sdist/wheel, attaches them to a GitHub Release, and
   prints the **`url`** and **`sha256`** for the formula in its job summary.
   (Or compute it yourself:)
   ```sh
   curl -sL https://github.com/ghostlyrvn/chronochrome/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256
   ```
4. **Update the formula** in both this repo's copy and the tap's
   `Formula/chronochrome.rb`: set `url` to the new tag and paste the new
   `sha256`. Push the tap.

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
