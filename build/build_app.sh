#!/bin/bash

TMP_DIR="/tmp/appbuild/"
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../" && pwd )"
# change working directory to root of project
cd $BASE_DIR

# these variables are set from app.json if found. Use app.json as single
# source of truth.
APP_VENDOR_DOMAIN="Cisco"
APP_ID="ExampleApp"
APP_VERSION="1.0"

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
            sys.exit(0)
except Exception as e: 
    print "fail: %s" % e
    sys.exit(1)
END`
if [ "$?" == "0" ] ; then
    for l in $out ; do eval "$l" ; done
fi

self=$0
app_pack="1.2_min"
docker_image=""
intro_video=""
private_key=""
enable_proxy="0"
relax_build_checks="0"
build_standalone="0"
standalone_http_port="5000"
standalone_https_port="5001"

# create version.txt with commit info
function add_version() {
    # example output:
    # 923797471c147b67b1e71004a8873d61db8d8f82      - commit
    # 2018-09-27T10:12:48-04:00                     - date (iso format)
    # 1538057568                                    - date (unix timestamp)
    # agccie@users.noreply.github.com               - commit author
    # master                                        - commit branch
    git log --pretty=format:%H%n%aI%n%at%n%ae%n -1 > ./version.txt
    git rev-parse --abbrev-ref HEAD >> ./version.txt
}

function log() {
    ts=`date '+%Y-%m-%dT%H:%M:%S'`
    echo "$ts $@"
}

# ensure build environment has all required tools to perform build
function check_build_tools() {
    build_type="$1"
    log "check build tools: $build_type"

    local frontend_req=()
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

    req=(
        "docker" 
    )
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


# build and deploy standalone container
function build_standalone_container() {
    set -e
    log "deploying standalone container $APP_VENDOR_DOMAIN/$APP_ID:$APP_VERSION"
    add_version

    # cp app.json to Service directory for consumption by config.py
    cp ./app.json ./Service/
    cp ./version.txt ./Service/ 

    # build docker container
    log "building container"
    docker_name=`echo "aci/$APP_ID:$APP_VERSION" | tr '[:upper:]' '[:lower:]'`
    container_name=`echo "$APP_ID\_$APP_VERSION" | tr '[:upper:]' '[:lower:]'`
    ba="--build-arg APP_MODE=0 "
    if [ "$enable_proxy" == "1" ] ; then
        if [ "$https_proxy" ] ; then ba="$ba --build-arg https_proxy=$https_proxy" ; fi
        if [ "$http_proxy" ] ; then ba="$ba --build-arg http_proxy=$http_proxy" ; fi
        if [ "$no_proxy" ] ; then ba="$ba --build-arg no_proxy=$no_proxy" ; fi
    fi
    log "cmd: docker build -t $docker_name $ba ./build/"
    docker build -t $docker_name $ba ./build/

    # run the container with volume mount based on BASE_DIR and user provided http and https ports
    local cmd="docker run -dit --name $container_name "
    cmd="$cmd -v $BASE_DIR/Service:/home/app/src/Service:ro "
    cmd="$cmd -v $BASE_DIR/UIAssets:/home/app/src/UIAssets:ro "
    cmd="$cmd -v $BASE_DIR/build:/home/app/src/build:ro "
    cmd="$cmd -p $standalone_http_port:80 "
    cmd="$cmd -p $standalone_https_port:443 "
    cmd="$cmd $docker_name "
    log "starting container: $cmd"
    eval $cmd
}


# build aci app
function build_app() {
    set -e
    log "building application $APP_VENDOR_DOMAIN/$APP_ID"
    add_version    

    # create workspace directory, setup required app-mode directories, and copy over required files
    log "building workspace/copying files to $TMP_DIR/$APP_ID"
    rm -rf $TMP_DIR/$APP_ID
    rm -rf $TMP_DIR/$APP_ID.build
    mkdir -p $TMP_DIR/$APP_ID/UIAssets
    mkdir -p $TMP_DIR/$APP_ID/Service
    mkdir -p $TMP_DIR/$APP_ID/Image
    mkdir -p $TMP_DIR/$APP_ID/ClusterMgrConfig
    mkdir -p $TMP_DIR/$APP_ID/Legal
    mkdir -p $TMP_DIR/$APP_ID/Media/Snapshots
    mkdir -p $TMP_DIR/$APP_ID/Media/Readme
    mkdir -p $TMP_DIR/$APP_ID/Media/License
    mkdir -p $TMP_DIR/$APP_ID.build
    
    # copy source code to service
    cp -rp ./Service/* $TMP_DIR/$APP_ID/Service/
    cp -p ./app.json $TMP_DIR/$APP_ID/
    # include app.json in Service directory for config.py to pick up required variables
    cp -p ./app.json $TMP_DIR/$APP_ID/Service/
    cp -p ./version.txt $TMP_DIR/$APP_ID/Service/
    # dynamically create clusterMgrConfig
    python ./cluster/apic/create_config.py > $TMP_DIR/$APP_ID/ClusterMgrConfig/clusterMgrConfig.json

    # create media and legal files
    # (note, snapshots are required in order for intro_video to be displayed on appcenter
    if [ "$(ls -A ./Legal)" ] ; then 
        cp -p ./Legal/* $TMP_DIR/$APP_ID/Legal/
    fi
    if [ "$(ls -A ./Media/Snapshots)" ] ; then 
        cp -p ./Media/Snapshots/* $TMP_DIR/$APP_ID/Media/Snapshots/
    fi
    if [ "$(ls -A ./Media/Readme)" ] ; then 
        cp -p ./Media/Readme/* $TMP_DIR/$APP_ID/Media/Readme/
    fi
    if [ "$(ls -A ./Media/License)" ] ; then 
        cp -p ./Media/License/* $TMP_DIR/$APP_ID/Media/License/
    fi

    if [ "$intro_video" ] ; then
        log "adding intro video $intro_video"
        mkdir -p $TMP_DIR/$APP_ID/Media/IntroVideo
        cp $intro_video $TMP_DIR/$APP_ID/Media/IntroVideo/IntroVideo.mp4
        chmod 777 $TMP_DIR/$APP_ID/Media/IntroVideo/IntroVideo.mp4
    elif [ -f ./Media/IntroVideo/IntroVideo.mp4 ] ; then 
        log "adding default intro video"
        mkdir -p $TMP_DIR/$APP_ID/Media/IntroVideo
        cp ./Media/IntroVideo/IntroVideo.mp4 $TMP_DIR/$APP_ID/Media/IntroVideo/IntroVideo.mp4
        chmod 777 $TMP_DIR/$APP_ID/Media/IntroVideo/IntroVideo.mp4
    fi

    # static UIAssets if present in project
    if [ "$(ls -A ./UIAssets)" ] ; then
        cp -rp ./UIAssets/* $TMP_DIR/$APP_ID/UIAssets/
        cp -p ./app.json $TMP_DIR/$APP_ID/UIAssets/
    fi

    # build docker container
    if [ "$docker_image" ] ; then
        log "saving docker container image to application"
        cp $docker_image > $TMP_DIR/$APP_ID/Image/aci_appcenter_docker_image.tgz
    else
        log "building container"
        docker_name=`echo "aci/$APP_ID:$APP_VERSION" | tr '[:upper:]' '[:lower:]'`
        if [ "$enable_proxy" == "1" ] ; then
            ba=""
            if [ "$https_proxy" ] ; then ba="$ba --build-arg https_proxy=$https_proxy" ; fi
            if [ "$http_proxy" ] ; then ba="$ba --build-arg http_proxy=$http_proxy" ; fi
            if [ "$no_proxy" ] ; then ba="$ba --build-arg no_proxy=$no_proxy" ; fi
            log "cmd: docker build -t $docker_name $ba --build-arg APP_MODE=1 ./"
            docker build -t $docker_name $ba --build-arg APP_MODE=1 ./build/
        else
            log "cmd: docker build -t $docker_name --build-arg APP_MODE=1 ./"
            docker build -t $docker_name --build-arg APP_MODE=1 ./build/
        fi
        log "saving docker container image to application"
        docker save $docker_name | gzip -c > $TMP_DIR/$APP_ID/Image/aci_appcenter_docker_image.tgz
    fi

    # execute packager
    log "packaging application"
    tar -zxf ./build/app_package/cisco_aci_app_tools-$app_pack.tar.gz -C $TMP_DIR/$APP_ID.build/ 
    if [ "$private_key" ] ; then
        python $TMP_DIR/$APP_ID.build/cisco_aci_app_tools-$app_pack/tools/aci_app_packager.py -f $TMP_DIR/$APP_ID -p $private_key
    else
        python $TMP_DIR/$APP_ID.build/cisco_aci_app_tools-$app_pack/tools/aci_app_packager.py -f $TMP_DIR/$APP_ID
    fi

    # cleanup
    rm -rf $TMP_DIR/$APP_ID.build
    rm -rf $TMP_DIR/$APP_ID
   
    log "build complete: `ls -a $TMP_DIR/*.aci`"

    set +e
}

# help options
function display_help() {
    echo ""
    echo "Help documentation for $self"
    echo "    -i docker image to bundled into app (.tgz format)"
    echo "    -h display this help message"
    echo "    -k private key uses for signing app"
    echo "    -P [https] https port when running in standalone mode"
    echo "    -p [http] http port when running in standalone mode"
    echo "    -r relax build checks (ensure tools are present but skip version check)"
    echo "    -s build and deploy container for standalone mode"
    echo "    -v path to intro video (.mp4 format)"
    echo "    -x send local environment proxy settings to container during build"
    echo ""
    exit 0
}


optspec=":i:v:k:p:P:hxrs"
while getopts "$optspec" optchar; do
  case $optchar in
    i)
        docker_image=$OPTARG
        if [ ! -f $docker_image ] ; then
            echo "" >&2
            echo "docker image '$docker_image' not found, aborting build" >&2
            echo "" >&2
            exit 1 
        fi
        ;;
    v) 
        intro_video=$OPTARG
        if [ ! -f $intro_video ] ; then
            echo "" >&2
            echo "intro video '$intro_video' not found, aborting build" >&2
            echo "" >&2
            exit 1
        fi
        ;;
    p)
        if [[ $OPTARG =~ ^-?[0-9]+$ ]] ; then
            standalone_http_port=$OPTARG
        else
            echo "" >&2
            echo "invalid http port $OPTARG, aborting build" >&2
            echo "" >&2
            exit 1
        fi
        ;;
    P)
        if [[ $OPTARG =~ ^-?[0-9]+$ ]] ; then
            standalone_https_port=$OPTARG
        else
            echo "" >&2
            echo "invalid http port $OPTARG, aborting build" >&2
            echo "" >&2
            exit 1
        fi
        ;;
    k)
        private_key=$OPTARG
        if [ ! -f $private_key ] ; then
            echo "" >&2
            echo "private key '$private_key' not found, aborting build" >&2
            echo "" >&2
            exit 1
        fi
        ;;
    x)
        enable_proxy="1"
        ;;
    r)
        relax_build_checks="1"
        ;;
    s)
        build_standalone="1"
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

# check depedencies first and then execute build
if [ "$build_standalone" == "1" ] ; then
    check_build_tools "backend"
    build_standalone_container
else
    check_build_tools 
    build_app
fi


