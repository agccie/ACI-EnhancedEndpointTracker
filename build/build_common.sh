#!/bin/bash

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/../"
# change working directory to root of project
cd $BASE_DIR

relax_build_checks="0"
app_pack="1.2_min"

# these variables are set from app.json if found. Use app.json as single
# source of truth.
APP_VENDOR_DOMAIN="Cisco"
APP_ID="ExampleApp"
APP_VERSION="1.0"
APP_FULL_VERSION="1.0.1"

# use python to read app.json and print each variable to stdout
out=`BASE_DIR="$BASE_DIR" python - <<END
import os, sys, json
fname = "%s/app.json" % os.environ["BASE_DIR"].strip()
try:
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
            sys.exit(0)
except Exception as e:
    print "fail: %s" % e
    sys.exit(1)
END`
if [ "$?" == "0" ] ; then
    for l in $out ; do eval "$l" ; done
fi

function log() {
    ts=`date '+%Y-%m-%dT%H:%M:%S'`
    echo "$ts $@"
}

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
                if [ "$relax_build_checks" == "1" ] ; then
                    log "'$p' version '$version', expected '$v', continuing anyways"
                else
                    echo "" >&2
                    echo "incompatible '$p' version '$version', expected '$v', aborting build" >&2
                    echo "" >&2
                    exit 1
                fi
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
                if [ "$relax_build_checks" == "1" ] ; then
                    log "'$p' version '$version', expected '$v', continuing anyways"
                else
                    echo "" >&2
                    echo "incompatible '$p' version '$version', expected '$v', aborting build" >&2
                    echo "" >&2
                    exit 1
                fi
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
