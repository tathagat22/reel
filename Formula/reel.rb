class Reel < Formula
  include Language::Python::Virtualenv

  desc "VCR for LLM APIs — record and replay OpenAI/Anthropic/Gemini calls"
  homepage "https://github.com/tathagat22/reel"
  url "https://files.pythonhosted.org/packages/source/r/reel/reel-0.1.0.tar.gz"
  # sha256 is filled in by the release runbook after `uv build` of the v0.1.0 tag
  sha256 "REPLACE_WITH_SDIST_SHA256_AT_RELEASE_TIME"
  license "Apache-2.0"

  depends_on "python@3.12"

  # Runtime deps. Versions are pinned conservatively to whatever the wheel
  # was tested with; bump as Reel's `pyproject.toml` advances.
  resource "httpx" do
    url "https://files.pythonhosted.org/packages/source/h/httpx/httpx-0.28.1.tar.gz"
    sha256 "REPLACE"
  end

  resource "starlette" do
    url "https://files.pythonhosted.org/packages/source/s/starlette/starlette-0.41.3.tar.gz"
    sha256 "REPLACE"
  end

  resource "uvicorn" do
    url "https://files.pythonhosted.org/packages/source/u/uvicorn/uvicorn-0.32.1.tar.gz"
    sha256 "REPLACE"
  end

  resource "typer" do
    url "https://files.pythonhosted.org/packages/source/t/typer/typer-0.14.0.tar.gz"
    sha256 "REPLACE"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/source/r/rich/rich-13.9.4.tar.gz"
    sha256 "REPLACE"
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/source/p/pydantic/pydantic-2.10.3.tar.gz"
    sha256 "REPLACE"
  end

  resource "jinja2" do
    url "https://files.pythonhosted.org/packages/source/j/jinja2/jinja2-3.1.4.tar.gz"
    sha256 "REPLACE"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"reel", "version"
    assert_match "reel #{version}", shell_output("#{bin}/reel version")
  end
end
