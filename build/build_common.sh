#!/bin/bash

function log() {
    ts=`date '+%Y-%m-%dT%H:%M:%S'`
    echo "$ts $@"
}

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/../"
# change working directory to root of project
cd $BASE_DIR

# packager version
app_pack="1.2_min"

# these variables are set from app.json if found. Use app.json as single
# source of truth.
APP_VENDOR_DOMAIN="Cisco"
APP_ID="ExampleApp"
APP_VERSION="1.0"
APP_FULL_VERSION="1.0.1"
APP_CONTAINER_NAMESPACE=""
APP_SHORT_NAME=""

# use python to read app.json and print each variable to stdout
out=`BASE_DIR="$BASE_DIR" python - <<END
import os, sys, json, traceback
try:
    fname = os.path.abspath("%s/app.json" % os.environ["BASE_DIR"].strip())
    if not os.path.exists(fname):
        fname = os.path.abspath("%s/Service/app.json" % os.environ["BASE_DIR"].strip())
    if os.path.exists(fname):
        with open(fname, "r") as f:
            js = json.load(f)
            if "vendordomain" in js:
                print "APP_VENDOR_DOMAIN=%s" % js["vendordomain"]
            if "appid" in js:
                print "APP_ID=%s" % js["appid"]
            if "version" in js:
                print "APP_VERSION=%s" % js["version"]
            if "full_version" in js:
                print "APP_FULL_VERSION=%s" % js["full_version"]
            if "container_namespace" in js:
                print "APP_CONTAINER_NAMESPACE=%s" % js["container_namespace"]
            if "short_name" in js:
                print "APP_SHORT_NAME=%s" % js["short_name"]
            sys.exit(0)
    else:
        raise Exception("file %s not found" % fname)
except Exception as e:
    print("\n%s" % traceback.format_exc())
    sys.exit(1)
END`
if [ "$?" == "1" ] ; then
    log "failed to read app.json: $out"
else
    for l in $out ; do eval "$l" ; done
fi   
# app container is required, if we failed to parse it then stop execution on script
if [ "$APP_CONTAINER_NAMESPACE" == "" ] || [ "$APP_SHORT_NAME" == "" ] ; then
    log "APP_CONTAINER_NAMESPACE=$APP_CONTAINER_NAMESPACE"
    log "APP_SHORT_NAME=$APP_SHORT_NAME"
    log "failed to determine CONTAINER_NAMESPACE/SHORT_NAME from app.json"
    exit 1
fi

# ensure build environment has all required tools to perform build
function check_build_tools() {
    build_type="$1"
    log "check build tools: $build_type"

    local frontend_req=(
        "node:v9.8.0"
        "npm:5.6.0"
    )
    local backend_req=(
        "docker"
    )
    local req=()

    if [ "$build_type" == "frontend" ] ; then
        req=("${frontend_req[@]}")
    elif [ "$build_type" == "backend" ] ; then
        req=("${backend_req[@]}")
    else
        # assume full app build which is frontend, backend, and packager
        req=("${frontend_req[@]}" "${backend_req[@]}")
        check_packager_dependencies
    fi

    log "checking following dependencies: ${req[@]}"

    for r in "${req[@]}"
    do
        IFS=":" read -r -a split <<< "$r"
        p=${split[0]}
        v=${split[1]}
        if [ ! `which $p` ] ; then
            echo "" >&2
            echo "requirement '$p' not installed, aborting build" >&2
            echo "(NOTE) if you are on a mac and 'file' is not found, install libmagic" >&2
            echo "" >&2
            exit 1
        fi
        # check version if provided (enforce exact version not minimum version)
        if [ "$v" ] ; then
            version=`$p -v`
            if [ ! "$version" == "$v" ] ; then
                log "'$p' version '$version', expected '$v', continuing anyways"
            fi
        fi
    done

    log "all build tool dependencies met"
}

function check_packager_dependencies() {
    # check app packager dependencies

    local req=(
        "pip"
        "file"
        "zip"
    )
    log "check app packager dependencies: $req"

    for r in "${req[@]}"
    do
        IFS=":" read -r -a split <<< "$r"
        p=${split[0]}
        v=${split[1]}
        if [ ! `which $p` ] ; then
            echo "" >&2
            echo "requirement '$p' not installed, aborting build" >&2
            echo "(NOTE) if you are on a mac and 'file' is not found, you can install libmagic" >&2
            echo "" >&2
            exit 1
        fi
        # check version if provided (enforce exact version not minimum version)
        if [ "$v" ] ; then
            version=`$p -v`
            if [ ! "$version" == "$v" ] ; then
                log "'$p' version '$version', expected '$v', continuing anyways"
            fi
        fi
    done

    # ensure user has installed packager cisco-aci-app-tools
    if [ ! `pip freeze 2> /dev/null | egrep "cisco-aci-app-tools" ` ] ; then
        echo "" >&2
        echo "Missing required python dependency 'cisco-aci-app-tools', aborting build" >&2
        echo "You can install via:" >&2
        echo "  pip install build/app_package/cisco_aci_app_tools-$app_pack.tar.gz" >&2
        echo "" >&2
        exit 1
    fi

    log "all app packager dependencies met"
}
