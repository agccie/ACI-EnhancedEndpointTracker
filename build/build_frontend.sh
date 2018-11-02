#!/bin/bash

# This script simplifies angular builds on container where src folder is mounted as read-only.
# Step (1): install

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/../"
# change working directory to root of project
cd $BASE_DIR
source $BASE_DIR/build/build_common.sh

TMP_DIR=""
SRC_DIR=""
DST_DIR=""
self=$0
relax_build_checks="0"
build_mode="standalone"

function build_frontend() {
    # build frontend from SRC_DIR and copy into DST_DIR
    log "build frontend (mode: $build_mode)"

    # check depedencies first and then execute build
    check_build_tools "frontend"

    # if src directory does not exist, exit.
    if [ ! -d $SRC_DIR ] ; then
        log "source directory $SRC_DIR not found"
        exit 1
    fi
    if [ ! -d $DST_DIR ] ; then
        log "create dst directory $TMP_DIR"
        mkdir -p $DST_DIR
    fi

    # copy source into tmp directory and perform build
    rm -r $TMP_DIR
    mkdir -p $TMP_DIR
    cp -rp $SRC_DIR/. $TMP_DIR/
    cd $TMP_DIR
    npm install
    if [ "$build_mode" == "app" ] ; then
        npm run build-app
        log "copying build dist to $DST_DIR"
        cp -rp $TMP_DIR/dist/. $DST_DIR/
        if [ -f $DST_DIR/index.html ] ; then
            # app mode requires app-start and app files where are identical to index.html
            # for this project...
            cp $DST_DIR/index.html $DST_DIR/app-start.html
            cp $DST_DIR/index.html $DST_DIR/app.html
        fi
    else
        npm run build-standalone
        log "copying build dist to $DST_DIR"
        cp -rp $TMP_DIR/dist/. $DST_DIR/
    fi
}

# help options
function display_help() {
    echo ""
    echo "Help documentation for $self"
    echo "    -s [path] frontend source code directory"
    echo "    -t [path] tmp directory to perform build"
    echo "    -d [path] final directory to cp build files"
    echo "    -m [mode] build frontend in app or standalone, default 'standalone'"
    echo "    -r relax build checks (ensure tools are present but skip version check)"
    echo ""
    exit 0
}

optspec=":s:t:d:m:hr"
while getopts "$optspec" optchar; do
  case $optchar in
    s)
        SRC_DIR=$OPTARG
        ;;
    t)
        TMP_DIR=$OPTARG
        ;;
    d)
        DST_DIR=$OPTARG
        ;;
    r)
        relax_build_checks="1"
        ;;
    m)
        build_mode=$OPTARG
        if [ "$build_mode" != "standalone" ] && [ "$build_mode" != "app" ] ; then
            echo "invalid build mode '$build_mode'." >&2
            exit 1
        fi
        ;;
    h)
        display_help
        exit 0
        ;;
    :)
        echo "Option -$OPTARG requires an argument." >&2
        exit 1
        ;;
    \?)
        echo "Invalid option: \"-$OPTARG\"" >&2
        exit 1
        ;;
  esac
done

build_frontend
