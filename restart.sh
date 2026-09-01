#!/bin/bash

if [ -z "$1" ]; then
  echo "Error: not exists"
  exit 1
fi

NAME="$1"

docker restart "$NAME"