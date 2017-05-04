#/bin/bash

# workers.sh
HELP="\n 
handler for dynamically starting/stoping/restarting all workers\n
    options\n
    -k      (opt)fabric_name, (opt) description\n
            stop one or all fabric monitors\n
    \n
    -ka \n
            stop all fabrics now without validation \n
    \n
    -s      (opt)fabric_name, (opt) description \n
            start one or more fabric monitors\n
    \n
    -r      (opt) fabric_name, (opt) description \n
            restart one or more fabric monitors\n
    \n
    -b \n
            bypass workers.sh and send all args directly to python \n
            note, script is run as background process\n
    \n
    -db \n
            check for successful connection to the database\n
"

# ensure we're executing in correct folder which is one directory above 
# current 'bash' directory where this script is located
cd ${0%/*}
cd ../

# python script to read config.py file
get_config_variable () {
PY_ARGS="$@" python - <<END
import os
config = {}

def import_attributes(filename):
    global config
    if os.path.exists(filename):
        with open(filename, "r") as f:
            exec(f, config)

def get_config(arg_str):
    global config
    import_attributes("config.py")
    import_attributes("instance/config.py")
    if len(arg_str) < 1:
        return ""
    if arg_str in config:
        return config[arg_str]
    return ""

args = os.environ['PY_ARGS'].strip()
print get_config(args)
END
}

# log directory from config file
LOG_DIR=`get_config_variable "LOG_DIR"`

# check for successful database connection
db_is_alive() {
    python -m app.tasks.ept.worker --check_db
    if [ "$?" == 0 ]; then
        echo "DB is alive"
        exit 0
    fi
    echo "DB is not alive"
    exit 1
}

# execute a fabric command requiring 2 arguments
#   $1 = command to execute (stop, start, restart)
#   $2 = fabric
fabric_command() {
    CMD="$1"
    FABRIC="$2"
    DESCR="$3"
    STATUS=""
    if [ "$CMD" ] ; then
        if [ "$CMD" != "start" -a $CMD != "stop" -a $CMD != "restart" ]; then
            echo "invalid command $CMD"
            exit 1
        fi
        if [ "$CMD" == "start" ] ; then
            STATUS="Starting"
        elif [ "$CMD" == "stop" ]; then
            STATUS="Stopping"
        else
            STATUS="Restarting"
        fi
        if [ "$FABRIC" == "" -o "$FABRIC" == "all" ] ; then
            rc=0
            # perform operation on each fabric individually
            for fab in `python -m app.tasks.ept.worker --get_fabrics`; do
                fabric_command $CMD $fab "$DESCR"
                if [ "$?" == "1" ]; then
                    rc=1
                fi
            done
            return $rc
        else
            # validate provided fabric and then perform operation
            python -m app.tasks.ept.worker --validate --fabric $FABRIC
            if [ "$?" == 0 ]; then
                # best effort, add the description 
                if [ "$DESCR" != "" ] ; then
                    python -m app.tasks.ept.worker --fabric $FABRIC --add_event_status $STATUS --add_event_description "$DESCR"
                fi
                if [ "$CMD" == "start" -o "$CMD" == "restart" ]; then
                    python -m app.tasks.ept.worker --$CMD --fabric $FABRIC 1>> $LOG_DIR/worker.stdout.log 2>> $LOG_DIR/worker.stderr.log &
                else
                    python -m app.tasks.ept.worker --$CMD --fabric $FABRIC
                fi
                if [ "$?" == "0" ]; then
                    echo "fabric $FABRIC $CMD success"
                    return 0
                else
                    echo "fabric $FABRIC $CMD fail"
                    return 1
                fi
            else
                echo "invalid fabric name \"$FABRIC\""
                return 1
            fi
        fi
    else
        echo "command required for fabric_command"
        exit 1
    fi 
}

# process arguments
if [ "$1" == "-h" ]; then
    echo -e $HELP
    exit 0
elif [ "$1" == "-db" ] ; then
    # check if database is alive
    db_is_alive 
elif [ "$1" == "-ka" ] ; then
    # kill/stop all fabrics now
    echo "stopping all fabrics"
    python -m app.tasks.ept.worker --stop
    exit "$?"
elif [ "$1" == "-k" ]; then
    # kill/stop one or more fabric monitor
    fabric_command stop $2 "$3"
    exit "$?"
elif [ "$1" == "-r" ]; then
    # restart one or more fabric monitor
    fabric_command restart $2 "$3"
    exit "$?"
elif [ "$1" == "-s" ]; then
    # restart one or more fabric monitor
    fabric_command start $2 "$3"
    exit "$?"
elif [ "$1" == "-b" ]; then
    # pass user arguments directly to python script
    python -m app.tasks.ept.worker "${@:2}" 1>> $LOG_DIR/worker.stdout.log 2>> $LOG_DIR/worker.stderr.log &
    exit 0
else
    echo "no arguments provided"
    echo "Use -h for more details"
    exit  1
fi
