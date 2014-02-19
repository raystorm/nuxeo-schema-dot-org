#!/bin/bash

if [[ -z "$@" ]]
then
    echo >&2 "usage: deploy.sh HOST"
    exit 1
fi

scp remote_deploy.sh $1:remote_deploy.sh
scp ../../../target/schema-dot-org-nuxeo-package.zip $1:schema-dot-org-nuxeo-package.zip
ssh $1 bash remote_deploy.sh
