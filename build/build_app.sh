#!/bin/bash

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/../"
# change working directory to root of project
cd $BASE_DIR
source $BASE_DIR/build/build_common.sh
TMP_DIR="/tmp/appbuild/"

self=$0
docker_image=""
intro_video=""
private_key=""
enable_proxy="0"
relax_build_checks="0"
build_standalone="0"
build_all_in_one="0"
standalone_http_port="5000"
standalone_https_port="5001"
docker_image_name=""            # set by build_standalone_container
external_docker_image_name=""   # set by user arg when using -a option

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

# build development standalone container
function build_standalone_container() {
    set -e
    log "building standalone container $APP_VENDOR_DOMAIN/$APP_ID:$APP_VERSION"
    add_version

    # cp app.json to Service directory for consumption by config.py
    cp ./app.json ./Service/
    cp ./version.txt ./Service/

    # build docker container
    log "building container"
    docker_image_name=`echo "aci/$APP_ID:$APP_VERSION" | tr '[:upper:]' '[:lower:]'`
    ba="--build-arg APP_MODE=0 "
    if [ "$enable_proxy" == "1" ] ; then
        if [ "$https_proxy" ] ; then ba="$ba --build-arg https_proxy=$https_proxy" ; fi
        if [ "$http_proxy" ] ; then ba="$ba --build-arg http_proxy=$http_proxy" ; fi
        if [ "$no_proxy" ] ; then ba="$ba --build-arg no_proxy=$no_proxy" ; fi
    fi
    log "cmd: docker build -t $docker_image_name $ba ./build/"
    docker build -t $docker_image_name $ba ./build/

}

# run container previously built by build_standalone_container
function run_standalone_container() {

    log "deploying standalone container $APP_VENDOR_DOMAIN/$APP_ID:$APP_VERSION"
    container_name=`echo "$APP_ID\_$APP_VERSION" | tr '[:upper:]' '[:lower:]'`
    # run the container with volume mount based on BASE_DIR and user provided http and https ports
    local cmd="docker run -dit --restart always --name $container_name "
    cmd="$cmd -v $BASE_DIR/Service:/home/app/src/Service:ro "
    cmd="$cmd -v $BASE_DIR/UIAssets:/home/app/src/UIAssets.src:ro "
    cmd="$cmd -v $BASE_DIR/build:/home/app/src/build:ro "
    if [ "$standalone_http_port" -gt "0" ] ; then
        cmd="$cmd -p $standalone_http_port:80 "
    fi
    if [ "$standalone_https_port" -gt "0" ] ; then
        cmd="$cmd -p $standalone_https_port:443 "
    fi
    cmd="$cmd $docker_image_name "
    log "starting container: $cmd"
    eval $cmd
}

# build_all_in_one_image function
# used to prep container image with bundled src code - executed from within container after git pull
# trigger build of container image that can be pushed to docker hub.  This first creates a docker
# image with the required dependencies using the ./build/Dockerfile. Then, it creates a new
# Dockerfile that references the new image, pulls the latest src within the container,
# executes the local internal build, and saves the finally container.
function build_all_in_one_image(){

    log "building all-in-one container image"
    set -e
    dockerfile=".tmpDocker"
    build_standalone_container
    # create tmp dockerfile
cat >$dockerfile <<EOL
FROM $docker_image_name
ENV SRC_DIR="/home/app/src"
# copy src into container
RUN mkdir -p \$SRC_DIR/Service && mkdir -p \$SRC_DIR/UIAssets.src && mkdir -p \$SRC_DIR/build
COPY ./Service/ \$SRC_DIR/Service/
COPY ./UIAssets/ \$SRC_DIR/UIAssets.src/
COPY ./build/ \$SRC_DIR/build/
# trigger frontend build
RUN \$SRC_DIR/build/build_frontend.sh -r \
    -s \$SRC_DIR/UIAssets.src \
    -d \$SRC_DIR/UIAssets \
    -t /tmp/build \
    -m standalone && \
    rm -rf /root/.npm && rm -rf /usr/lib/node_modules && rm -rf /tmp/build

WORKDIR \$SRC_DIR/Service
CMD \$SRC_DIR/Service/start.sh
EXPOSE 443/tcp
EOL
    # build container image
    local cmd="docker build -t $external_docker_image_name -f $dockerfile ."
    log "executing docker build: $cmd"
    eval $cmd
    rm -f $dockerfile
}

# used to prep container image with bundled src code - executed from within container after git pull
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

    # build docker container
    if [ "$docker_image" ] ; then
        log "saving docker container image to application"
        cp $docker_image > $TMP_DIR/$APP_ID/Image/aci_appcenter_docker_image.tgz
        docker_image_name=$docker_image
    else
        log "building container"
        docker_image_name=`echo "aci/$APP_ID:$APP_VERSION" | tr '[:upper:]' '[:lower:]'`
        if [ "$enable_proxy" == "1" ] ; then
            ba=""
            if [ "$https_proxy" ] ; then ba="$ba --build-arg https_proxy=$https_proxy" ; fi
            if [ "$http_proxy" ] ; then ba="$ba --build-arg http_proxy=$http_proxy" ; fi
            if [ "$no_proxy" ] ; then ba="$ba --build-arg no_proxy=$no_proxy" ; fi
            log "cmd: docker build -t $docker_image_name $ba --build-arg APP_MODE=1 ./"
            docker build -t $docker_image_name $ba --build-arg APP_MODE=1 ./build/
        else
            log "cmd: docker build -t $docker_image_name --build-arg APP_MODE=1 ./"
            docker build -t $docker_image_name --build-arg APP_MODE=1 ./build/
        fi
        log "saving docker container image to application"
        docker save $docker_image_name | gzip -c > $TMP_DIR/$APP_ID/Image/aci_appcenter_docker_image.tgz
    fi

    # copy source code to service
    cp -rp ./Service/* $TMP_DIR/$APP_ID/Service/
    cp -p ./app.json $TMP_DIR/$APP_ID/
    # include app.json in Service directory for config.py to pick up required variables
    cp -p ./app.json $TMP_DIR/$APP_ID/Service/
    cp -p ./version.txt $TMP_DIR/$APP_ID/Service/
    # dynamically create clusterMgrConfig
    conf=$TMP_DIR/$APP_ID/ClusterMgrConfig/clusterMgrConfig.json
    python ./cluster/apic/create_config.py --image $docker_image_name > $conf

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

    # this project performs frontend angular build from source in UIAssets
    if [ "$(ls -A ./UIAssets)" ] ; then
        mkdir -p $TMP_DIR/$APP_ID.build/UIAssets
        local bf_tmp="$TMP_DIR/$APP_ID.build/UIAssets/"
        local bf_src="$BASE_DIR/UIAssets/"
        local bf_dst="$TMP_DIR/$APP_ID/UIAssets/"
        if [ "$SKIP_FRONTEND" == "1" ] ; then
            log "skipping frontend build, adding minimum files to support packaging"
            echo "hello" > $bf_dst/app.html
            echo "hello" > $bf_dst/app-start.html
            cp -p $BASE_DIR/UIAssets/logo.png $bf_dst
        else
            ./build/build_frontend.sh -s $bf_src -d $bf_dst -t $bf_tmp -m "app"
            # need to manually copy over logo.png into UIAssets folder
            if [ -f "$BASE_DIR/UIAssets/logo.png" ] ; then
                cp -p $BASE_DIR/UIAssets/logo.png $bf_dst
            fi
        fi
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

    #log "build complete: `ls -a $TMP_DIR/*.aci`"
    set +e
}


# help options
function display_help() {
    echo ""
    echo "Help documentation for $self"
    echo "    -a [name] build all-in-one container image (used for creating docker hub image only)"
    echo "    -i [image] docker image to bundled into app (.tgz format)"
    echo "    -h display this help message"
    echo "    -k [file] private key uses for signing app"
    echo "    -P [https] https port when running in standalone mode (use 0 to disable)"
    echo "    -p [http] http port when running in standalone mode (use 0 to disable)"
    echo "    -r relax build checks (ensure tools are present but skip version check)"
    echo "    -s build and deploy container for standalone mode"
    echo "    -v [file] path to intro video (.mp4 format)"
    echo "    -x send local environment proxy settings to container during build"
    echo ""
    exit 0
}


optspec=":i:v:k:p:P:a:hxrs"
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
    k)
        private_key=$OPTARG
        if [ ! -f $private_key ] ; then
            echo "" >&2
            echo "private key '$private_key' not found, aborting build" >&2
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
    x)
        enable_proxy="1"
        ;;
    r)
        relax_build_checks="1"
        ;;
    s)
        build_standalone="1"
        ;;
    a)
        build_all_in_one="1"
        external_docker_image_name=$OPTARG
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

if [ "$APP_FULL_VERSION" == "" ] ; then
    APP_FULL_VERSION=$APP_VERSION
fi
app_original_filename=$APP_VENDOR_DOMAIN-$APP_ID-$APP_VERSION.aci
app_final_filename=$APP_VENDOR_DOMAIN-$APP_ID-$APP_FULL_VERSION.aci
# reset APP_VERSION to APP_FULL_VERSION for docker info to reflect patch
APP_VERSION=$APP_FULL_VERSION

# check depedencies first and then execute build
if [ "$build_standalone" == "1" ] ; then
    check_build_tools "backend"
    build_standalone_container
    run_standalone_container
elif [ "$build_all_in_one" == "1" ] ; then
    build_all_in_one_image
else
    check_build_tools
    build_app
    if [ -f $TMP_DIR/$app_original_filename ] ; then
        mv $TMP_DIR/$app_original_filename ./$app_final_filename
    elif [ -f $TMP_DIR/$app_final_filename ] ; then
        mv $TMP_DIR/$app_final_filename ./$app_final_filename
    fi
    log "build complete: $app_final_filename"

fi

