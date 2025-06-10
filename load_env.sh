#!/bin/bash

#Exit on error
set -e

#Enable automatic export of environment variables
set -a

#Load variables from .env file
source .env
echo $OAUTH2_PROXY_SCOPE
#Disable automatic export
set +a