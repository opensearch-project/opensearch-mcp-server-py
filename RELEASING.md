# Releasing

This document explains how to release a new version of opensearch-mcp-server-py to [PyPI](https://pypi.org/project/opensearch-mcp-server-py/), [Docker Hub](https://hub.docker.com/r/opensearchproject/opensearch-mcp-server-py) and [Amazon ECR Public](https://gallery.ecr.aws/opensearchproject/opensearch-mcp-server-py).

## Branches and tags

- `main` is where development happens.
- Each minor version has a release branch named `<major>.<minor>`, for example `0.12`. Patch releases are cut from the same branch.
- Release tags are the plain version with no `v` prefix, for example `0.12.0`. The tag must match `version` in [pyproject.toml](pyproject.toml).

## Release steps

1. Update `version` in [pyproject.toml](pyproject.toml) and move the `Unreleased` entries in [CHANGELOG.md](CHANGELOG.md) under the new version. Merge the change.
2. Create or update the release branch, for example `0.13`, from the commit to release.
3. Open a release request in [opensearch-project/.github](https://github.com/opensearch-project/.github/issues) asking an admin to create the tag, for example `0.13.0`, on the release branch.
4. Pushing the tag starts the [Release Workflow](.github/workflows/publish-release.yml). A maintainer approves the run in the `release-approval` environment. The workflow then:
   1. Builds the package and publishes it to PyPI with trusted publishing.
   2. Builds the `linux/amd64` and `linux/arm64` image and pushes `opensearchstaging/opensearch-mcp-server-py:<version>` to Docker Hub staging.
   3. Creates a GitHub pre-release with generated release notes.
5. Publishing the pre-release triggers the Jenkins [release pipeline](jenkins/release.jenkinsFile). It copies the staging image to `opensearchproject/opensearch-mcp-server-py` and `public.ecr.aws/opensearchproject/opensearch-mcp-server-py`, tagged both `<version>` and `latest`.
6. When Jenkins finishes, it opens an issue titled `[Release - Action Required] Publish release for tag <version>`. A maintainer verifies the artifacts, then edits the GitHub pre-release, clears **Set as a pre-release**, and publishes it as the latest release.

## Verify the release

- PyPI: `pip install opensearch-mcp-server-py==<version>` and check `pip show opensearch-mcp-server-py`.
- Docker Hub and ECR: `docker run --rm -i opensearchproject/opensearch-mcp-server-py:<version> < /dev/null` and `docker run --rm -i public.ecr.aws/opensearchproject/opensearch-mcp-server-py:<version> < /dev/null` both exit 0.

## Error handling

- If a job in the Release Workflow fails, fix the cause and use **Re-run failed jobs** on the workflow run. PyPI does not accept the same version twice, so once the PyPI job has succeeded, re-run the later jobs rather than recreating the tag.
- If the Jenkins pipeline fails, it opens a `[RELEASE] Failed: release for tag <version>` issue. Fix the cause and ask an admin to re-run the Jenkins job.
