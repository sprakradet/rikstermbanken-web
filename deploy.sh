#!/bin/sh

cd $(dirname $0)

tag="$1"

if [ "x$tag" == "x" ]; then
    echo "Ange en tagg: $0 <tagg>"
    exit 1
fi

/usr/bin/git fetch || exit 1
/usr/bin/git checkout --detach "tags/$tag" || exit 1
/usr/bin/git status || exit 1

exec ./deploy-finalize.sh
