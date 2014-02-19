#!/bin/bash

export NUXEO_CONF=/etc/nuxeo/nuxeo.conf
NUXEOCTL=/var/lib/nuxeo/server/bin/nuxeoctl

sudo service nuxeo stop
sudo -Eu nuxeo $NUXEOCTL mp-uninstall --accept=true schema-dot-org
sudo -Eu nuxeo $NUXEOCTL mp-install --accept=true schema-dot-org-nuxeo-package.zip
sudo service nuxeo start
