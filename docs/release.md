# Release runbook

The one-page playbook for cutting a Reel release. Automated by `.github/workflows/release.yml` for the PyPI half; Homebrew is currently manual until the install count justifies a tap.

## Prerequisites — one-time, then forget

1. **Create a PyPI project + Trusted Publisher.**
   - Reserve the name: <https://pypi.org/manage/account/publishing/>
   - Add a "pending publisher" pointing at:
     - Repository: `tathagat22/reel`
     - Workflow: `release.yml`
     - Environment: `pypi`
   - In the GitHub repo settings, create an environment named `pypi` (Settings → Environments → New environment). Optional: require reviewers before deploys.

2. **Verify the workflow file** is at `.github/workflows/release.yml`. It's already present in this repo.

## Per-release flow

```bash
# 1. Bump the version in two places
$EDITOR pyproject.toml          # update [project].version
$EDITOR src/reel/__init__.py    # update __version__

# 2. Confirm the build is clean
make check && uv build && ls dist/

# 3. Update the docs/CHANGELOG entry (when the file exists)

# 4. Commit + tag
git commit -am "release: v0.1.0"
git tag v0.1.0
git push origin main v0.1.0

# 5. GitHub Actions takes over:
#    - Builds sdist + wheel
#    - Verifies the tag matches pyproject's version (refuses mismatched tags)
#    - Publishes to PyPI via Trusted Publishing (no API token needed)
#    - Creates a GitHub Release with the artifacts attached
```

Watch the run: <https://github.com/tathagat22/reel/actions/workflows/release.yml>

## Homebrew formula update

The formula at `Formula/reel.rb` is currently stubbed with `REPLACE` placeholders for `sha256` checksums. After the PyPI publish succeeds:

```bash
# 1. Get the sha256 of the published sdist
curl -sL "https://files.pythonhosted.org/packages/source/r/reel/reel-0.1.0.tar.gz" | shasum -a 256

# 2. Update Formula/reel.rb with that sdist sha256 (the resource shas are computed by `brew bump-formula-pr` automatically if you push to homebrew-core)
$EDITOR Formula/reel.rb

# 3. Test locally
brew install --build-from-source ./Formula/reel.rb
brew test reel
brew audit --strict --new ./Formula/reel.rb
```

To submit to `homebrew-core` (recommended once Reel has >50 GitHub stars or any meaningful install base, per Homebrew's notability criteria):

```bash
brew tap homebrew/core --force
brew bump-formula-pr --strict --url=https://files.pythonhosted.org/packages/source/r/reel/reel-0.1.0.tar.gz reel
```

Until that happens, users can install from this repo with a manual `tap`:

```bash
brew install tathagat22/reel/reel
# Where the tap repo is `tathagat22/homebrew-reel` containing Formula/reel.rb
```

## Sanity checklist before tagging

- [ ] `make check` is green locally
- [ ] CI is green on `main` for the same commit you're tagging
- [ ] `uv build` produces both sdist and wheel; `dist/` size feels sane
- [ ] Version bumped in **both** `pyproject.toml` and `src/reel/__init__.py`
- [ ] At least one entry in the changelog (or PR titles since the last tag)
- [ ] Tagged version doesn't already exist on PyPI (PyPI rejects re-uploads — burn that namespace once)
- [ ] You're tagging from `main`, not a feature branch

## Aborting a botched release

If something publishes wrong, **don't try to overwrite on PyPI** — PyPI doesn't allow re-uploads at the same version. Instead:

```bash
# 1. Delete the broken tag + GitHub release (PyPI artifact stays, but you yank it)
git tag -d v0.1.0
git push origin :v0.1.0
gh release delete v0.1.0 --yes --cleanup-tag

# 2. Yank the broken version on PyPI (still visible, but not picked by `pip install reel`)
#    Done via the PyPI web UI: https://pypi.org/manage/project/reel/release/0.1.0/

# 3. Bump to the next patch (e.g., 0.1.1), commit the fix, tag, re-run the flow.
```

Yanking is the standard practice; deleting from PyPI is generally not allowed and bad form even when it is.
