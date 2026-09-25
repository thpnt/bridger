# Releasing Bridger

1. Merge release-ready changes to `main`.
2. Configure PyPI Trusted Publishing for `usebridger` with owner `thpnt`, repository `bridger`, workflow `release.yml`, and environment `pypi`.
3. Create the GitHub environment named `pypi`.
4. Validate the skills with `gh skill publish --dry-run`.
5. Create and publish the GitHub release `v0.1.0` from the matching commit. The release workflow checks that its tag matches `pyproject.toml` before building.
6. Confirm the release workflow publishes `usebridger` to PyPI.
7. Verify a clean installation with `uv tool install usebridger` and `bridger --help`.
8. Publish the matching skills separately with `gh skill publish --tag skills-v0.1.0`, then install them from the `thpnt/bridger` repository pinned to that tag:

   ```sh
   gh skill install thpnt/bridger bridger --pin skills-v0.1.0
   gh skill install thpnt/bridger bridger-graph --pin skills-v0.1.0
   gh skill install thpnt/bridger bridger-setup --pin skills-v0.1.0
   ```

The skill release uses a separate tag because `gh skill publish` creates its own GitHub release. The PyPI workflow only processes stable `vMAJOR.MINOR.PATCH` tags.
