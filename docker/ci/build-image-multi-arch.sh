#!/bin/bash

# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

set -e

function usage() {
    echo "Usage: $0 -v TAG_NAME -r REPOSITORY [-a PLATFORMS]"
    echo ""
    echo "Required:"
    echo "  -v TAG_NAME     Image tag (e.g. 0.9.0)"
    echo "  -r REPOSITORY   Docker repository (e.g. opensearchstaging)"
    echo ""
    echo "Optional:"
    echo "  -a PLATFORMS    Comma-separated platforms (default: linux/amd64,linux/arm64)"
    exit 1
}

PLATFORMS="linux/amd64,linux/arm64"

while getopts ":hv:r:a:" arg; do
    case $arg in
        v) TAG_NAME=$OPTARG ;;
        r) REPOSITORY=$OPTARG ;;
        a) PLATFORMS=$OPTARG ;;
        h) usage ;;
        ?) echo "Invalid option: -${OPTARG}"; usage ;;
    esac
done

if [ -z "$TAG_NAME" ] || [ -z "$REPOSITORY" ]; then
    echo "Error: -v TAG_NAME and -r REPOSITORY are required."
    usage
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
IMAGE="${REPOSITORY}/opensearch-mcp-server-py"

echo "Building ${IMAGE}:${TAG_NAME} for platforms: ${PLATFORMS}"

docker buildx create --use --name osb-builder 2>/dev/null || true

docker buildx build \
    --platform "${PLATFORMS}" \
    --build-arg VERSION="${TAG_NAME}" \
    --push \
    --tag "${IMAGE}:${TAG_NAME}" \
    --tag "${IMAGE}:latest" \
    -f "${REPO_ROOT}/Dockerfile" \
    "${REPO_ROOT}"

echo "Successfully pushed ${IMAGE}:${TAG_NAME} and ${IMAGE}:latest"
