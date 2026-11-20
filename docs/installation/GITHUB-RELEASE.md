# GitHub publication runbook

Review source, historical git objects and hosted CI before publication.
Rotate any previously disclosed credentials; do not copy live solver keys into
ordinary pull-request CI. Public verification uses offline test fixtures.

## Repository settings

| Setting | Value |
| --- | --- |
| Repository | `ohobs-science-pipeline` |
| Display name | OHOBS Science Pipeline |
| Project | Open Horizon Observatory (OHOBS) |
| Description | Astronomical FITS calibration, uncertainty propagation, image quality assessment, and astrometric validation. |
| License | BSD-3-Clause |
| Default branch | `main` |
| Visibility after approval | Public |
| Topics | astronomy, astrophysics, fits, astrometry, scientific-python, open-science, observatory, telescope, ccd-calibration, photometry |

The current configured remote is https://github.com/realifyed/ohobs-science-pipeline.git.
Verify the intended destination before publication. For a new public source import, create an empty repository
with no auto-generated README, license, or ignore file. Use the GitHub
web interface or GitHub CLI's interactive authentication. Enable private
vulnerability reporting after creating the repository.

## First push from the reviewed source export

Extract the delivered source ZIP into a separate directory. This is a
first public import from the audited tree. The original local repository,
its legitimate history and its original RC2 tag stay preserved. Its older
commits contain a private observing filename. A normal push of that history
would publish the old filename as well.

After authorization, run from the extracted source directory:

```powershell
git init --initial-branch=main
git add -- .
git diff --cached --check
git diff --cached --stat
git commit -m "Import audited OSP 0.1.0rc2 public source"
git remote add origin https://github.com/realifyed/ohobs-science-pipeline.git
git remote -v
git push -u origin main
```

Inspect the staged files and
remote URL before continuing. If the destination is already populated,
inspect its history and coordinate the import with the owner. Keep the
existing remote configuration intact.

## Release assets

Review hosted CI before publishing release assets. In the first public
repository, create the RC2 tag only if that tag does not already exist and
the checked-out public commit matches the delivered source export. The
existing historical RC2 tag is kept in the development repository.

```powershell
git status --short
git ls-remote --tags origin refs/tags/v0.1.0rc2
git tag -a v0.1.0rc2 -m "OSP 0.1.0rc2 scientific software pre-release"
git push origin refs/tags/v0.1.0rc2
```

Use the four distributions, source ZIP and `SHA256SUMS.txt` as release
assets. In PowerShell, set the asset location to the extracted delivery
directory containing `RELEASE-NOTES.md`:

```powershell
$assets = 'PATH_TO_EXTRACTED_RELEASE_BUNDLE'
$releaseAssets = @(Get-ChildItem -LiteralPath $assets -File |
    Where-Object Name -Match '\.(whl|tar\.gz|zip)$|^SHA256SUMS\.txt$' |
    ForEach-Object FullName)
gh release create v0.1.0rc2 @releaseAssets --verify-tag --draft --prerelease --latest=false --title "OHOBS Science Pipeline v0.1.0rc2" --notes-file (Join-Path $assets RELEASE-NOTES.md)
```

Review the draft and publish only after approval. If an existing published
tag refers to different source, leave it intact and use a new release
version. Keep wheels and source distributions as release assets.

[GitHub's initial-push guide](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) and
[GitHub CLI release options](https://cli.github.com/manual/gh_release_create)
cover the hosted steps.
