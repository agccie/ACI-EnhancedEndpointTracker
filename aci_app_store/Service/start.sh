#!/bin/bash

# APP name
APP_VENDOR="Cisco"
APP_APPID="EnhancedEndpointTracker"

# ACI App start.sh required for starting components within container
SRC_DIR="/home/app/src/Service"
DATA_DIR="/home/app/data"
LOG_DIR="/home/app/log"
CRED_DIR="/home/app/credentials"
PRIVATE_CONFIG="/home/app/config.py"
LOG_FILE="$LOG_DIR/start.log"
STARTED_FILE="$DATA_DIR/.started"

# Logging levels for reference
LOGGING_LEVEL_DEBUG=10
LOGGING_LEVEL_INF0=20
LOGGING_LEVEL_WARN=30
LOGGING_LEVEL_ERROR=40
LOGGING_LEVEL_CRITICAL=50

exit_script(){
    # force script to exit after timeout
    TIMEOUT=10
    echo "$(date) exit in $TIMEOUT seconds" >> $LOG_FILE
    sleep $TIMEOUT
    exit 1
}

setup_directories() {
    # required dictories for logging and database datastore
    mkdir $LOG_DIR/ept/ -p
    mkdir $LOG_DIR/mongo/ -p
    mkdir $LOG_DIR/apache2/ -p
    mkdir $DATA_DIR/db -p    
    
    chown mongodb:mongodb $DATA_DIR/db -R
    chown mongodb:mongodb $LOG_DIR/mongo/ -R
    chown www-data:www-data $LOG_DIR/ept -R
    chown www-data:www-data $LOG_DIR/apache2 -R
}

setup_logrotate() {
    # setup logrotate for apache, mongo, and ept files
    echo "
$LOG_DIR/apache2/*.log {
    missingok
    rotate 10
    size 5M
    compress
    delaycompress
    notifempty
    sharedscripts
    postrotate
                if /etc/init.d/apache2 status > /dev/null ; then \\
                    /etc/init.d/apache2 reload > /dev/null; \\
                fi;
    endscript
    prerotate
        if [ -d /etc/logrotate.d/httpd-prerotate ]; then \\
            run-parts /etc/logrotate.d/httpd-prerotate; \\
        fi; \\
    endscript
}

$LOG_DIR/mongo/*.log {
       size 5M
       rotate 10
       copytruncate
       delaycompress
       compress
       notifempty
       missingok
}

$LOG_DIR/ept/*.log {
       size 50M
       rotate 10
       copytruncate
       compress
       notifempty
       missingok
}

" > /etc/logrotate.d/aci_app

}

setup_environment() {
    # setup app required environment variables
    CONFIG_FILE="$SRC_DIR/instance/config.py"
    echo "" > $CONFIG_FILE
    echo "EMAIL_SENDER=\"noreply@aci.app\"" >> $CONFIG_FILE
    echo "LOG_DIR=\"$LOG_DIR/ept/\"" >> $CONFIG_FILE
    echo "LOG_LEVEL=$LOGGING_LEVEL_DEBUG" >> $CONFIG_FILE
    # log rotate built into docker environment, therefore,
    # disable python log rotate
    echo "LOG_ROTATE=0" >> $CONFIG_FILE
    echo "LOGIN_ENABLED=0" >> $CONFIG_FILE
    echo "ACI_APP_MODE=1" >> $CONFIG_FILE
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
}

ALL_RUNNING=1
IS_RUNNING=0
check_service() {
    # set global IS_RUNNING to 1 if process is running
    COUNT=`ps -ef | egrep $1 | egrep -v grep | wc -l`
    if [ "$COUNT" -ge "1" ] ; then
        echo "$(date) service $1 is running" >> $LOG_FILE
        IS_RUNNING=1
    else
        echo "$(date) service $1 is NOT running" >> $LOG_FILE
        IS_RUNNING=0
    fi
}

recover_service() {
    # perform recovery operations for services that support recovery
    SERVICE=$1
    echo "$(date) attempting recovery for service $SERVICE" >> $LOG_FILE
    if [ "$SERVICE" == "mongodb" ] ; then
        mongod --repair --dbpath $DATA_DIR/db >> $LOG_FILE 2>> $LOG_FILE
        service $SERVICE start >> $LOG_FILE 2>> $LOG_FILE
        check_service $SERVICE
        if [ "$IS_RUNNING" == "0" ] ; then
            # one last attempt, remove local db copy and lock file
            rm -fv $DATA_DIR/db/mongod.lock >> $LOG_FILE 2>> $LOG_FILE
            rm -rfv $DATA_DIR/db/local\.* >> $LOG_FILE 2>> $LOG_FILE
            rm -rfv $DATA_DIR/db/journal* >> $LOG_FILE 2>> $LOG_FILE
            chown mongodb:mongodb $DATA_DIR/db -R >> $LOG_FILE 2>> $LOG_FILE
            service $SERVICE start >> $LOG_FILE 2>> $LOG_FILE
        fi
    else
        echo "$(date) no recovery mechanism for service $SERVICE"
    fi
}

start_service() {
    # start a service with restart and recover if it fails on start
    # if it can't be started, set ALL_RUNNING to 0
    SERVICE=$1
    echo "$(date) starting service $SERVICE" >> $LOG_FILE
    service $SERVICE start >> $LOG_FILE 2>> $LOG_FILE
    check_service $SERVICE
    if [ "$IS_RUNNING" == "0" ] ; then
        echo "$(date) restarting service $SERVICE" >> $LOG_FILE
        service $SERVICE restart >> $LOG_FILE 2>> $LOG_FILE
        check_service $SERVICE
        if [ "$IS_RUNNING" == "0" ] ; then
            echo "$(date) failed to restart service $SERVICE" >> $LOG_FILE
            recover_service $SERVICE 
            check_service $SERVICE
            if [ "$IS_RUNNING" == "0" ] ; then
                echo "$(date) recover service $SERVICE failed" >> $LOG_FILE
                ALL_RUNNING=0
            fi
        fi
    fi
}

start_services() {
    # start required services
    CRON=`which cron`
    echo "$(date) starting cron: $CRON" >> $LOG_FILE
    $CRON >> $LOG_FILE 2>>$LOG_FILE
    start_service "apache2" 
    start_service "mongodb"
    start_service "exim4"
}

BASH=`which bash`
MAX_WAIT_COUNT=200
WAIT_TIME=3
wait_for_mongo() {
    # after creating a new database or on initial boot/restart
    # mongo may be rebuilding journal/database which prevents it from
    # accepting new connections. If mongo is running, wait until it 
    # accepts the new connection
    echo "$(date) ensuring mongo is ready to accept database connections" >> $LOG_FILE
    i="0"
    while [ $i -lt "$MAX_WAIT_COUNT" ] ; do
        echo "$(date) mongodb check count: $i" >> $LOG_FILE
        check_service "mongodb"
        if [ "$IS_RUNNING" == "0" ] ; then
            echo "$(date) mongodb is not running! Trying to restart it..." >> $LOG_FILE
            start_service "mongodb"
            if [ "$ALL_RUNNING" == "0" ] ; then
                echo "$(date) failed to restarting mongodb, exiting..." >> $LOG_FILE
                exit_script 
            fi
        fi
        CMD="$BASH $SRC_DIR/bash/workers.sh -db"
        echo "$(date) checking db connection: $CMD" >> $LOG_FILE
        sudo -u www-data $CMD >> $LOG_FILE 2>> $LOG_FILE
        if [ "$?" == "0" ] ; then
            echo "$(date) successfully connected to mongodb" >> $LOG_FILE
            return
        else
            echo "$(date) failed to connect to mongodb" >> $LOG_FILE
        fi
        echo "$(date) mongodb is not ready, sleeping for $WAIT_TIME seconds" >> $LOG_FILE
        sleep $WAIT_TIME
        i=$[$i+1]
    done 

    echo "$(date) failed to connect to mongodb after max($i) iterations" >> $LOG_FILE
    exit_script
}

setup_app() {
    # pause to ensure mongo is ready to accept connections
    wait_for_mongo

    # execute setup_db script in conditional mode to setup database
    # if not previously setup.
    APP_USERNAME=${APP_VENDOR}_${APP_APPID}
    SETUP_ARGS="--conditional --no_verify --no_https --username=admin2 --password=cisco"
    echo "$(date) python $SRC_DIR/setup_db.py $SETUP_ARGS " >> $LOG_FILE 2>> $LOG_FILE
    sudo -u www-data python $SRC_DIR/setup_db.py $SETUP_ARGS >> $LOG_FILE 2>> $LOG_FILE
    if [ "$?" == "1" ] ; then
        echo "$(date) An error occurred during setup_db" >> $LOG_FILE
        exit_script
    fi

    # pause again since database setup my trigger file preallocator to restart
    wait_for_mongo

    # separate script to perform apic_app_init
    SETUP_ARGS="--apic_app_username=$APP_USERNAME --apic_app_init"
    echo "$(date) python $SRC_DIR/setup_db.py $SETUP_ARGS " >> $LOG_FILE 2>> $LOG_FILE
    sudo -u www-data python $SRC_DIR/setup_db.py $SETUP_ARGS >> $LOG_FILE 2>> $LOG_FILE
    if [ "$?" == "1" ] ; then
        echo "$(date) An error occurred during apic_app_init" >> $LOG_FILE
        exit_script
    fi

    # start all configured fabrics
    sudo -u www-data /bin/bash $SRC_DIR/bash/workers.sh -s all "Triggered by APIC start.sh"  >> $LOG_FILE 2>> $LOG_FILE
    if [ "$?" == "1" ] ; then
        echo "$(date) An error occurred starting workers - contining anyways" >> $LOG_FILE
    fi

    # just in case any directories have incorrect permission from setup, rewrite them
    setup_directories
}

run() {
    # successfully started at this point
    echo "$(date) set started flag" >> $LOG_FILE
    touch $STARTED_FILE >> $LOG_FILE 2>> $LOG_FILE

    # app expects start.sh to run as a daemon process
    # for now we only use it to start services so just need to keep
    # it alive in big while loop
    while true; do sleep 60 ; done
}

echo "======================================================================" >> $LOG_FILE
echo "$(date) Restarting... " >> $LOG_FILE
echo "======================================================================" >> $LOG_FILE
echo "$(date) === clear started flag " >> $LOG_FILE
rm $STARTED_FILE >> $LOG_FILE 2>> $LOG_FILE
echo "$(date) === setup directories " >> $LOG_FILE
setup_directories
echo "$(date) === setting up environment variables" >> $LOG_FILE
setup_environment
echo "$(date) === setup logrotate" >> $LOG_FILE
setup_logrotate
echo "$(date) === starting services" >> $LOG_FILE
start_services
if [ "$ALL_RUNNING" == "0" ] ; then
    echo "$(date) One or more services failed to start..." >> $LOG_FILE
    exit_script
fi
echo "$(date) pausing 10 seconds to ensure all services initialize" >> $LOG_FILE
sleep 10
echo "$(date) === setting up app" >> $LOG_FILE
setup_app
echo "$(date) === Running" >> $LOG_FILE
run
