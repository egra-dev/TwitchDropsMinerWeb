#!/bin/bash

if [ -z "$1" ]; then
  echo "Error: parameter not specified"
  exit 1
fi

NAME="$1"

docker restart "$NAME"