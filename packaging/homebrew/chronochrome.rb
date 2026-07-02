# Source-of-truth copy of the Homebrew formula.
#
# This repo is NOT itself a tap. To publish, copy this file to
# `Formula/chronochrome.rb` in the tap repo `ghostlyrvn/homebrew-chronochrome`
# (see packaging/homebrew/HOMEBREW.md). Keeping the canonical copy here means
# the formula is version-controlled next to the code it installs.
#
# Before each release: bump `url` to the new tag and replace `sha256` with the
# checksum of that tag's source tarball. The release workflow
# (.github/workflows/release.yml) prints the correct sha256 in its logs, or run:
#
#   curl -sL https://github.com/ghostlyrvn/chronochrome/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256
#
class Chronochrome < Formula
  include Language::Python::Virtualenv

  desc "Swap editor color themes based on time-of-day blocks"
  homepage "https://github.com/ghostlyrvn/chronochrome"
  url "https://github.com/ghostlyrvn/chronochrome/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "REPLACE_WITH_SHA256_OF_THE_v0.1.0_TARBALL"
  license "MIT"

  depends_on "python@3.12"

  # Zero runtime dependencies (stdlib only), so there are no `resource` blocks
  # to vendor — this builds straight from the project's own sdist.
  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "chronochrome 0.1.0", shell_output("#{bin}/chronochrome --version")

    # `validate` exercises config loading + the scheduler end-to-end.
    (testpath/"config.toml").write <<~TOML
      check_interval_minutes = 5

      [[blocks]]
      name = "all-day"
      start = "06:00"
      end = "06:00"
      [blocks.themes]
      zed = "One Light"
    TOML
    system bin/"chronochrome", "--config", testpath/"config.toml", "validate"

    # `adapters` runs without a config and lists the Zed adapter.
    assert_match "zed", shell_output("#{bin}/chronochrome adapters")
  end
end
