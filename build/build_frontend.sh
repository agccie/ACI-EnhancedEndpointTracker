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
    log "creating tmp directory for frontend build at: $TMP_DIR"
    rm -rf $TMP_DIR
    mkdir -p $TMP_DIR
    cp -rp $SRC_DIR/. $TMP_DIR/
    # remove node_modules cached if present in tmp working directory
    rm -rf $TMP_DIR/node_modules
    cd $TMP_DIR
    npm install
    if [ "$build_mode" == "app" ] || [ "$build_mode" == "app-mini" ] ; then
        if [ "$build_mode" == "app-mini" ] ; then
            log "executing 'npm run build-app-mini'"
            npm run build-app-mini
        else
            log "executing 'npm run build-app'"
            npm run build-app
        fi
        log "copying build dist to $DST_DIR"
        if [ "$(ls -A $TMP_DIR/dist)" ] ; then
            cp -rp $TMP_DIR/dist/. $DST_DIR/
            if [ -f $DST_DIR/index.html ] ; then
                # app mode requires app-start and app files where are identical to index.html
                # for this project...
                cp $DST_DIR/index.html $DST_DIR/app-start.html
                cp $DST_DIR/index.html $DST_DIR/app.html
            fi
        else
            log "app build FAILED"
            return 1
        fi
    else
        log "executing 'npm run build-standalone'"
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
    echo ""
    exit 0
}

optspec=":s:t:d:m:h"
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
    m)
        build_mode=$OPTARG
        if [ "$build_mode" != "standalone" ] && [ "$build_mode" != "app" ]  && [ "$build_mode" != "app-mini" ] ; then
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
