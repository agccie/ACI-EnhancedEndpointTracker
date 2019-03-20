#!/bin/bash

# startup script for app_mode on APIC or standalone application. This script runs in all-in-one mode
# by default in which all services are started. Else, a specific role and optional arguments are 
# provided to startup a subset of services.
#   1) cron     ( required for services for logrotate )
#   2) apache2  (role web)
#       If HOSTED_PLATFORM=APIC then update apache2 config file listen on only WEB_PORT for https.
#   3) redis    (role redis)
#   4) mongo    (role db)
#   5) mgr/watcher/worker (role X, identity Y)

# force start.sh to be executed in base of Service directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# this variables should already be set within container but creating defaults just in case
self=$0
role="all-in-one"
identity=""
worker_count=10
log_rotate=0
stdout=0
no_exit=0
APP_MODE=${APP_MODE:-0}
APP_DIR=${APP_DIR:-/home/app}
DATA_DIR=${DATA_DIR:-/home/app/data}
LOCAL_DATA_DIR=${LOCAL_DATA_DIR:-/home/app/local-data}
LOG_DIR=${LOG_DIR:-/home/app/log}
SRC_DIR="$APP_DIR/src/Service"
CRED_DIR="$APP_DIR/credentials"
PRIVATE_CONFIG="$APP_DIR/config.py"
LOG_FILE="$LOG_DIR/start.log"
STARTED_FILE="$APP_DIR/.started"
STATUS_FILE="$APP_DIR/.status"
MONGO_CONFIG="/etc/mongod.conf"
MONGO_MAX_WAIT_COUNT=50

# required services to start
ALL_SERVICES=(
    "apache2"
    "cron" 
    "mongodb"
    "redis-server"
)

# log message to stdout and to logfile
function log(){
    ts=`date '+%Y-%m-%dT%H:%M:%S'`
    echo "$ts $@"
    if [ "$stdout" == "0" ] ; then
        if [ "$LOG_FILE" ] ; then
         echo "$ts $@" >> $LOG_FILE 2> /dev/null
        fi
    fi
}

# update value in status file 
# this is a single line file with a description of the current startup status
function set_status(){
    ts=`date '+%Y-%m-%dT%H:%M:%S'`
    log "status: $1"
    if [ "$STATUS_FILE" ] ; then
        echo "($ts) $1" > $STATUS_FILE 2> /dev/null
    fi
}

function set_running(){
    # update started flag and start running
    log `touch $STARTED_FILE 2>&1`
    set_status "running"
}

# force script to exit after timeout
function exit_script(){
    local timeout=10
    log "exiting in $timeout seconds"
    sleep $timeout
    log "exit"
    if [ "$no_exit" == "1" ] ; then
        log "no exit enabled, sleep forever"
        sleep infinity 
    else
        exit 1
    fi
}

# required dictories for logging and database datastore (all-in-one-mode)
function setup_directories() {
    set_status "setting up backend directories"

    # if base directories do not exists, then something has gone terribly wrong...
    critical=( $APP_DIR $LOG_DIR $DATA_DIR $SRC_DIR )
    for d in "${critical[@]}" ; do
        if [ ! -d $d ] ; then
            set_status "error: required directory $d not found"
            exit_script
        fi
        log "directory $d found"
    done

    # use local data directory for db to avoid gluster issues
    if [ ! -d $DATA_DIR/db ] ; then
        log "create $DATA_DIR/db"
        mkdir -p $DATA_DIR/db
    fi
    # use local data directory for db to avoid gluster issues
    if [ ! -d $LOCAL_DATA_DIR/db ] ; then
        log "create $LOCAL_DATA_DIR/db"
        mkdir -p $LOCAL_DATA_DIR/db
    fi
    if [ ! -d $LOG_DIR/mongo ] ; then
        log "create $LOG_DIR/mongo"
        mkdir -p $LOG_DIR/mongo/
    fi
    if [ ! -d $LOG_DIR/apache2 ] ; then
        log "create $LOG_DIR/apache2"
        mkdir -p $LOG_DIR/apache2/ 
    fi
    # update log/db file permissions
    chown mongodb:mongodb $DATA_DIR/db -R
    chown mongodb:mongodb $LOCAL_DATA_DIR/db -R
    chown mongodb:mongodb $LOG_DIR/mongo/ -R
    chown www-data:www-data $LOG_DIR/apache2 -R
    chown www-data:www-data $LOG_DIR/*.log
    chmod 777 $LOG_DIR/*.log
    chmod 777 $LOG_DIR
}

#  check if provided service is running.  return 1 (error) if not running
function service_is_running(){
    # if no service provided then return error
    local service=$1
    if [ ! "$service" ] ; then return 1 ; fi
    local count=`ps -ef | egrep $service | egrep -v grep | wc -l`
    if [ "$count" -ge "1" ] ; then
        log "service $service is running"
        return 0
    else
        log "error: service $service is NOT running"
        return 1
    fi
}

# start a particular service and return error code on failure
function start_service(){
    local service=$1
    local sleep_time=5
    if [ ! "$service" ] ; then return 1 ; fi
    set_status "starting service $service"
    log `service $service start 2>&1`
    # wait a few seconds before checking service is running
    log "pause $sleep_time seconds before checking service status"
    sleep $sleep_time
    if ! service_is_running $service ; then
        set_status "error: failed to start service $service"
        return 1
    fi
    # for mongo, ensure we can connect to the db
    if [ "$service" == "mongodb" ] ; then
        if ! mongodb_accept_connections ; then
            return 1
        fi
    fi
    return 0
}

# start required backend services and check status to ensure successfully started
function start_all_services(){
    set_status "starting all services"
    for s in "${ALL_SERVICES[@]}" ; do
        if ! start_service $s ; then
            log "failed to start service $s"
            exit_script
        else
            log "successfully started service $s"
        fi
    done
}

# ensure mongo db is accepting new connections.  It may take a few minutes on 
# slow filesystems when allocating db chunks or rebuilding from journaling
function mongodb_accept_connections(){
    local wait_time=3
    local i="0"
    local cmd="cd $SCRIPT_DIR ; python -m app.models.aci.worker --stdout check_db "
    if [ "$stdout" == "0" ] ; then
        cmd="$cmd >> $LOG_FILE"
    fi
    while [ $i -lt "$MONGO_MAX_WAIT_COUNT" ] ; do
        set_status "checking mongodb is accepting connections $i/$MONGO_MAX_WAIT_COUNT"
        log "command: $cmd"
        if su - -s /bin/bash www-data -c "$cmd" ; then
            log "successfully connected to database"
            return 0
        else
            log "failed to connected to database"
        fi
        log "mongodb is not ready, sleeping for $wait_time seconds"
        sleep $wait_time
        i=$[$i+1]
    done 
    set_status "failed to connect to mongodb after $i attempts"
    return 1
}

# setup app required environment variables
function create_app_config_file() {
    set_status "creating app config_file"

    local instance_config="$SRC_DIR/instance"
    local config_file="$instance_config/config.py"
    if [ ! -d $instance_config ] ; then 
        mkdir -p $instance_config
    fi

    # in app mode on APIC it's possible that multiple processes will try to create the config
    # file. To prevent the race condition, only create it if not already present. This requires
    # build logic to initialize an empty config file
    if [ "$HOSTED_PLATFORM" == "APIC" ] ; then
        if [ -s $config_file ] ; then
            log "app config already exists"
            return 0
        fi
    fi

    # app mode specific settings
    if [ "$APP_MODE" == "1" ] ; then
        echo "" > $config_file
        echo "LOG_DIR=\"$LOG_DIR/\"" >> $config_file
        echo "LOG_ROTATE=0" >> $config_file
        echo "ACI_APP_MODE=1" >> $config_file
        echo "LOGIN_ENABLED=0" >> $config_file
        # update iv and ev against seed
        echo "" > $PRIVATE_CONFIG
        if [ -s "$CRED_DIR/plugin.key" ] && [ -s "$CRED_DIR/plugin.crt" ] ; then
            KEY=`cat $CRED_DIR/plugin.key $CRED_DIR/plugin.crt | md5sum | egrep -o "^[^ ]+"`
            echo "EKEY=\"$KEY\"" >> $PRIVATE_CONFIG
        fi
        if [ -s "$CRED_DIR/plugin.key" ] ; then
            EIV=`cat $CRED_DIR/plugin.key | md5sum | egrep -o "^[^ ]+"`
            echo "EIV=\"$EIV\"" >> $PRIVATE_CONFIG
        fi
    fi
    # if running as app-infra, update db, redis, and proxy info (apache doesn't pick up env)
    if [ "$HOSTED_PLATFORM" == "APIC" ] ; then
        log "updating $config_file with app-infra settings"
        echo "REDIS_HOST=\"$REDIS_HOST\"" >> $config_file
        echo "REDIS_PORT=$REDIS_PORT" >> $config_file
        echo "MONGO_HOST=\"$MONGO_HOST\"" >> $config_file
        echo "MONGO_PORT=$MONGO_PORT" >> $config_file
        echo "PROXY_URL=\"https://localhost:$WEB_PORT\"" >> $config_file
    elif [ "$HOSTED_PLATFORM" == "SWARM" ] ; then
        log "updating $config_file with swarm settings"
        echo "REDIS_HOST=\"$REDIS_HOST\"" >> $config_file
        echo "REDIS_PORT=$REDIS_PORT" >> $config_file
        echo "MONGO_HOST=\"$MONGO_HOST\"" >> $config_file
        echo "MONGO_PORT=$MONGO_PORT" >> $config_file
        echo "PROXY_URL=\"http://localhost:80\"" >> $config_file
    fi
    chmod 755 $config_file
}

# execute db init scripts (all-in-one mode)
function init_db() {
    set_status "initializing db"

    local setup_args=""
    local cmd=""
    # app mode specific settings
    if [ "$APP_MODE" == "1" ] ; then
        setup_args="--apic_app_init "
    fi
    cmd="python $SCRIPT_DIR/setup_db.py $setup_args"
    if [ "$stdout" == "1" ] ; then
        cmd="$cmd --stdout"
    fi
    log "command: $cmd"
    if su - -s /bin/bash www-data -c "$cmd" ; then
        log "successfully initialized db"
    else
        set_status "error: failed to initialize db"
        exit_script
    fi
}

function update_apache() {
    set_status "updating apache config"
    if [ "$WEB_PORT" == "" ] ; then
        log "error: WEB_PORT env not set"
        return 1
    else
        # update listening ports
        ports="/etc/apache2/ports.conf"
        echo "" > $ports
        echo "<IfModule ssl_module>" >> $ports
        echo "  Listen $WEB_PORT" >> $ports
        echo "</IfModule>" >> $ports
        echo "<IfModule mod_gnutls.c>" >> $ports
        echo "  Listen $WEB_PORT" >> $ports
        echo "</IfModule>" >> $ports
        # update disable 000-default to prevent locked ports, and restart ssl-default
        ssl_conf="/etc/apache2/sites-available/default-ssl.conf"
        sed -i -E "s/_default_:[0-9]+/_default_:$WEB_PORT/" $ssl_conf
        /usr/sbin/a2dissite 000-default
        /usr/sbin/a2dissite default-ssl 
        /usr/sbin/a2ensite default-ssl
    fi
}

function poll_web() {
    # continuous poll web to ensure it is still alive, stop on error
    set_status "poll web"
    while true ; do
        if ! curl -sk https://localhost:$WEB_PORT/api/app-status/ > /dev/null ; then
            log "error: web poll failed(1)"
            log `curl -k https://localhost:$WEB_PORT/api/app-status/`
            sleep 5
            if ! curl -sk https://localhost:$WEB_PORT/api/app-status/ ; then
                log "error: web poll failed(2) - quit"
                return 1
            else
                log "web connectivity successfully resumed"
            fi
        fi
        sleep 600
    done
}

# run db cluster (mongos, cfg-srv, and shards in single container - used in APP_MODE on APIC)
function run_db_cluster() {
    # create a folder for cfg and each shard then start each service
    set_status "run db cluster" 

    # check for required env variables first
    required_env=( "LOCAL_REPLICA" "DB_SHARD_COUNT" "DB_MEMORY" "DB_CFG_SRV" )    
    for e in "${required_env[@]}" ; do
        if [[ ! "${!e}" =~ [0-9a-zA-Z] ]] ; then
            log "error: required env $e not set"
            log `env`
            return 1
        fi
    done
    # calculate base port used for mongos, cfg, and each shard
    db_port="DB_PORT_$LOCAL_REPLICA"
    db_port="${!db_port}"
    if [ "$db_port" == "" ] ; then
        log "error: env DB_PORT_$LOCAL_REPLICA not set"
        return 1
    fi

    # all mongo logging to mongo directory
    MONGO_LOG_DIR="$LOG_DIR/mongo/$LOCAL_REPLICA"
    if [ ! -d $MONGO_LOG_DIR ] ; then
        log "create $MONGO_LOG_DIR"
        mkdir -p $MONGO_LOG_DIR
    fi

    # setup files and start cfg
    MONGO_DATA_DIR="$LOCAL_DATA_DIR/db/$LOCAL_REPLICA"
    if [ ! -d $MONGO_DATA_DIR/cfg ] ; then
        log "creating $MONGO_DATA_DIR/cfg"
        mkdir -p $MONGO_DATA_DIR/cfg
    fi
    cfg_port=$[$db_port+1]
    cmd="/usr/bin/mongod --configsvr --replSet cfg "
    cmd="$cmd --bind_ip_all --port $cfg_port --dbpath $MONGO_DATA_DIR/cfg "
    cmd="$cmd --wiredTigerCacheSizeGB $DB_MEMORY "
    if [ "$stdout" == "0" ] ; then
        cmd="$cmd --logpath $MONGO_LOG_DIR/cfg.log --logappend"
    fi
    cmd="$cmd &"
    log "starting cfg server: $cmd"
    eval $cmd

    # create directory for each shard and start service
    shard="0"
    while [ $shard -lt $DB_SHARD_COUNT ] ; do
        log "setting up shard $shard"
        if [ ! -d $MONGO_DATA_DIR/sh$shard ] ; then
            log "creating $MONGO_DATA_DIR/sh$shard"
            mkdir -p $MONGO_DATA_DIR/sh$shard
        fi
        shard_port=$[$shard+1+$cfg_port]
        cmd="/usr/bin/mongod --shardsvr --replSet sh$shard "
        cmd="$cmd --bind_ip_all --port $shard_port --dbpath $MONGO_DATA_DIR/sh$shard "
        cmd="$cmd --wiredTigerCacheSizeGB $DB_MEMORY "
        if [ "$stdout" == "0" ] ; then
            cmd="$cmd --logpath $MONGO_LOG_DIR/sh$shard.log --logappend"
        fi
        cmd="$cmd &"
        log "starting shard $shard: $cmd"
        eval $cmd
        shard=$[$shard+1]
    done

    # start mongos last, exit if mongos stops running
    cmd="/usr/bin/mongos --configdb $DB_CFG_SRV "
    cmd="$cmd --bind_ip_all --port $db_port "
    if [ "$stdout" == "0" ] ; then
        cmd="$cmd --logpath $MONGO_LOG_DIR/mongos.log --logappend "
    fi
    log "starting mongos server: $cmd"
    eval $cmd
}

# run an individual db role (mongos, cfg, or single shard/replica) in swarm mode
function run_db_single_role(){
    # create a folder for cfg and each shard then start each service
    set_status "run db single role" 

    # check for required env variables first
    required_env=(  "LOCAL_REPLICA" "LOCAL_SHARD" "LOCAL_PORT" 
                    "DB_SHARD_COUNT" "DB_MEMORY" "DB_CFG_SRV" "DB_ROLE")    
    for e in "${required_env[@]}" ; do
        if [[ ! "${!e}" =~ [0-9a-zA-Z] ]] ; then
            log "error: required env $e not set"
            log `env`
            return 1
        fi
    done

    # all mongo logging to mongo directory
    MONGO_LOG_DIR="$LOG_DIR/mongo/$LOCAL_REPLICA"
    if [ ! -d $MONGO_LOG_DIR ] ; then
        log "create $MONGO_LOG_DIR"
        mkdir -p $MONGO_LOG_DIR
    fi
    # data directory path
    MONGO_DATA_DIR="$LOCAL_DATA_DIR/db/$LOCAL_REPLICA"

    if [ "$DB_ROLE" == "mongos" ] ; then
        # start mongos last, exit if mongos stops running
        cmd="/usr/bin/mongos --configdb $DB_CFG_SRV "
        cmd="$cmd --bind_ip_all --port $LOCAL_PORT "
        if [ "$stdout" == "0" ] ; then
            cmd="$cmd --logpath $MONGO_LOG_DIR/mongos.log --logappend "
        fi

    elif [ "$DB_ROLE" == "configsvr" ] ; then
        if [ ! -d $MONGO_DATA_DIR/cfg ] ; then
            log "creating $MONGO_DATA_DIR/cfg"
            mkdir -p $MONGO_DATA_DIR/cfg
        fi
        cmd="/usr/bin/mongod --configsvr --replSet cfg "
        cmd="$cmd --bind_ip_all --port $LOCAL_PORT --dbpath $MONGO_DATA_DIR/cfg "
        cmd="$cmd --wiredTigerCacheSizeGB $DB_MEMORY "
        if [ "$stdout" == "0" ] ; then
            cmd="$cmd --logpath $MONGO_LOG_DIR/cfg.log --logappend "
        fi

    elif [ "$DB_ROLE" == "shardsvr" ] ; then
        if [ ! -d $MONGO_DATA_DIR/sh$LOCAL_SHARD ] ; then
            log "creating $MONGO_DATA_DIR/sh$LOCAL_SHARD"
            mkdir -p $MONGO_DATA_DIR/sh$LOCAL_SHARD
        fi
        cmd="/usr/bin/mongod --shardsvr --replSet sh$LOCAL_SHARD "
        cmd="$cmd --bind_ip_all --port $LOCAL_PORT --dbpath $MONGO_DATA_DIR/sh$LOCAL_SHARD "
        cmd="$cmd --wiredTigerCacheSizeGB $DB_MEMORY "
        if [ "$stdout" == "0" ] ; then
            cmd="$cmd --logpath $MONGO_LOG_DIR/sh$LOCAL_SHARD.log --logappend "
        fi
    else
        log "error: invalid DB_ROLE: $DB_ROLE"
        return 1
    fi
    
    log "starting $DB_ROLE: $cmd"
    eval $cmd
}

# init replica set with continuous retry
function init_rs(){
    local rs=$1
    local configsvr=$2
    while true ; do
        set_status "init replica set $rs"
        cmd="python $SCRIPT_DIR/setup_db.py --init_rs $rs $configsvr"
        if [ "$stdout" == "1" ] ; then
            cmd="$cmd --stdout"
        fi
        log "command: $cmd"
        if `eval $cmd` ; then
            log "successfully initiated replica set $rs"
            return 0
        else
            log "failed to initiate replica set $rs, retrying in 10 seconds..."
            sleep 10
        fi
    done
}

# init db cluster
function init_db_cluster() {
    # this function needs to first initialize cfg and replica sets, add shards, and then setup db 
    set_status "init db cluster" 
    local setup_args=""
    local cmd=""
    # check for required env variables first
    required_env=( "DB_SHARD_COUNT" "DB_CFG_SRV" )    
    for e in "${required_env[@]}" ; do
        if [[ ! "${!e}" =~ [0-9a-zA-Z] ]] ; then
            log "error: required env $e not set"
            log `env`
            return 1
        fi
    done
    # init replica set for cfg server
    init_rs $DB_CFG_SRV --configsvr
    # init replica set for each shard
    shard="0"
    while [ $shard -lt $DB_SHARD_COUNT ] ; do
        shardname="DB_RS_SHARD_$shard"
        log "setup replica set for shard $shard"
        if [[ ! "${!shardname}" =~ [0-9a-zA-Z] ]] ; then
            log "error: required env $shardname not set"
            return 1
        fi
        init_rs ${!shardname}
        shard=$[$shard+1]
    done
    # now that all replia sets are initialized, add each shard to db
    shard="0"
    while [ $shard -lt $DB_SHARD_COUNT ] ; do
        shardname="DB_RS_SHARD_$shard"
        log "adding shard $shard to db: $shardname: ${!shardname}"
        cmd="python $SCRIPT_DIR/setup_db.py --add_shard ${!shardname}"
        if [ "$stdout" == "1" ] ; then
            cmd="$cmd --stdout"
        fi
        log "command: $cmd"
        if ! `eval $cmd` ; then
            log "failed to add shard to db"
            return 1
        fi
        shard=$[$shard+1]
    done
    
    # finally, setup db and discover apic
    set_status "setting up db"
    if [ "$APP_MODE" == "1" ] ; then
        setup_args="--apic_app_init "
    fi
    cmd="python $SCRIPT_DIR/setup_db.py --sharding $setup_args"
    if [ "$stdout" == "1" ] ; then
        cmd="$cmd --stdout"
    fi
    log "command: $cmd"
    if ! `eval $cmd` ; then
        log "failed to setup db"
        return 1
    fi 
}

# execute ept main to start mgmr and workers, return if script exits
function run_all_in_one_mgr_workers() {
    set_status "starting mgr with $worker_count workers"
    cd $SCRIPT_DIR
    if [ "$stdout" == "0" ] ; then
        python -m app.models.aci.ept.main --all-in-one --count $worker_count >> $LOG_FILE 2>> $LOG_FILE 
    else
        python -m app.models.aci.ept.main --all-in-one --count $worker_count --stdout
    fi
    log "unexpected mgr exit"
}

# ensure identity was provided, else exit script
function validate_identity() {
    if [ "$identity" == "" ] ; then
        log "validate identity failed, identity not provided"
        exit_script
    fi
}

# main container startup
function main(){
    # update LOG_FILE to unique service name if HOSTED_PLATFORM set and not all-in-one
    if [ "$role" != "all-in-one" ] ; then
        if [ "$HOSTED_PLATFORM" == "APIC" ]  || [ "$HOSTED_PLATFORM" == "SWARM" ] ; then
            LOG_FILE="$LOG_DIR/start_$role"
            if [ "$LOCAL_REPLICA" != "" ] ; then
                LOG_FILE="$LOG_FILE-$LOCAL_REPLICA"
            fi
            LOG_FILE="$LOG_FILE.log"
        fi
    fi

    log "======================================================================"
    set_status "restarting ($role)"
    log "======================================================================"
    log `rm -f $STARTED_FILE 2>&1`
    log "env: `env`"

    # setup required directories with proper write access and custom app config
    setup_directories
    create_app_config_file

    # if log_rotate is enabled, start cron
    if [ "$log_rotate" == "1" ] ; then
        start_service "cron"
    fi

    # execute requested role
    if [ "$role" == "all-in-one" ] ; then
        # stdout not supported in all-in-one mode
        if [ "$stdout" == "1" ] ; then 
            log "stdout not supported in all-in-one mode, disabling stdout"
            stdout="0"
        fi
        start_all_services
        init_db
        set_running
        run_all_in_one_mgr_workers
        log "sleeping..."
        sleep infinity 
    elif [ "$role" == "web" ] ; then
        if [ "$HOSTED_PLATFORM" == "APIC" ] ; then
            if ! update_apache ; then
                log "error: failed to update apache config"
                exit_script
            fi
        fi
        # no easy way to force apache2 logs to stdout, warn the user and move on...
        if [ "$stdout" == "1" ] ; then
            log "web role currently ignores stdout option"
        fi
        if ! start_service "apache2" ; then
            log "error: failed to start apache"
            exit_script
        fi
        set_running
        poll_web
    elif [ "$role" == "redis" ] ; then
        # start redis and stop if it exits
        cmd="/usr/bin/redis-server --bind 0.0.0.0 "
        if [ "$REDIS_PORT" == "" ] ; then
            log "error: REDIS_PORT not set, using default"
        else
            cmd="$cmd --port $REDIS_PORT "
        fi
        set_running
        cmd="$cmd --maxclients 10000"
        if [ "$stdout" == "0" ] ; then
            cmd="$cmd --logfile $LOG_DIR/redis-server.log"
        fi
        log "starting redis: $cmd"
        log `eval $cmd 2>&1`
    elif [ "$role" == "db" ] ; then
        # setup db files and start each db service, exits on error
        set_running
        if [ "$HOSTED_PLATFORM" == "APIC" ] ; then
            run_db_cluster 
        else
            run_db_single_role
        fi
    elif [ "$role" == "mgr" ] ; then
        # init db cluster (replicas and conditional db setup with sharding), then start 
        validate_identity
        if ! init_db_cluster ; then
            log "failed to init db cluster"
            exit_script
        fi
        set_running
        cd $SCRIPT_DIR
        if [ "$stdout" == "0" ] ; then
            python -m app.models.aci.ept.main --role manager --id $identity >> $LOG_FILE 2>> $LOG_FILE 
        else
            python -m app.models.aci.ept.main --role manager --id $identity --stdout
        fi
    elif [ "$role" == "watcher" ] ; then
        # run watcher script
        validate_identity
        set_running
        cd $SCRIPT_DIR
        if [ "$stdout" == "0" ] ; then
            python -m app.models.aci.ept.main --role watcher --id $identity >> $LOG_FILE 2>> $LOG_FILE 
        else
            python -m app.models.aci.ept.main --role watcher --id $identity --stdout
        fi
    elif [ "$role" == "worker" ] ; then
        # run worker script
        validate_identity
        set_running
        cd $SCRIPT_DIR
        if [ "$stdout" == "0" ] ; then
            python -m app.models.aci.ept.main --role worker --id $identity --count $worker_count >> $LOG_FILE 2>> $LOG_FILE 
        else
            python -m app.models.aci.ept.main --role worker --id $identity --count $worker_count --stdout
        fi
    else
        log "error: unknown startup role '$role'"
    fi

    set_status "error: unexpected exit"
    exit_script
}


# help options
function display_help() {
    echo ""
    echo "Help documentation for $self"
    echo "    -r [role] role to execute (defaults to all-in-one)"
    echo "              options: web, db, redis, mgr, watcher, worker, all-in-one"
    echo "    -c [count] number of workers to run when executing all-in-one mode"
    echo "    -i [identity] manager/worker identity"
    echo "    -l enable log rotation"
    echo "    -s send all output to stdout"
    echo "    -a always active (do not exit on error)"
    echo ""
    exit 0
}

optspec=":r:c:i:lash"
while getopts "$optspec" optchar; do
  case $optchar in
    r)
        role=$OPTARG
        ;;
    c)
        worker_count=$OPTARG
        ;;
    l)
        log_rotate="1"
        ;;
    i)
        identity=$OPTARG
        ;;
    a)
        no_exit="1"
        ;;
    s)
        stdout="1"
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

# execute main 
main
