# Release process

A release is made with one command, from an up-to-date `main`:

```
scripts/release.sh            # version chosen from the commits since the last tag
scripts/release.sh minor      # or patch / major / v2.5.0 to force it
```

The script:

1. checks that the working tree is clean, on `main` and in sync with GitHub;
2. runs the tests when the test environment is installed (`pip install -r requirements_test.txt`); the Tests
   workflow runs them on GitHub in any case;
3. refuses to go on if the `## Unreleased` section of `CHANGELOG.md` is empty;
4. proposes the next version (patch, or minor when a `feat` commit or branch was merged, or major on a breaking
   change) and asks for confirmation;
5. sets `version` in `custom_components/open_firenet/manifest.json` (the version Home Assistant shows) and renames
   the `## Unreleased` section to `## vX.Y.Z (date)`;
6. commits, pushes, then creates and pushes the tag.

The pushed tag starts the Release workflow, which checks that `manifest.json` carries the version of the tag and
creates the GitHub release **as a draft**, with the notes of that version's section of `CHANGELOG.md`.

Last step, by hand: open the draft on GitHub, adjust the title and the notes, and click **Publish release**. HACS
only sees published releases.

## Day to day

Every `feat` or `fix` adds a line under `## Unreleased` in `CHANGELOG.md`, in English, written for users. The section
is created again by the first entry after a release.

Do not create a release or a tag from the GitHub page: `manifest.json` and the changelog would be left behind (this is
what happened with v2.4.1).
