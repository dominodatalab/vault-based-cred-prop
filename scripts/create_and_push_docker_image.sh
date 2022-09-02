#!/bin/bash
set -e
echo "USAGE: ./create_and_push_docker_image.sh VERSION"
image="${image:-quay.io/domino/vault-creds-prop}"
version=$1
docker build -f ./Dockerfile -t $image:$version .
docker push $image:$version

