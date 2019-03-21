# VERSION 2.0
FROM ubuntu:18.04

MAINTAINER Andy Gossett, agossett@cisco.com

ARG APP_MODE=0
ENV APP_MODE $APP_MODE
ENV APP_DIR "/home/app"
ENV DATA_DIR "$APP_DIR/data"
ENV LOCAL_DATA_DIR "$APP_DIR/local-data"
ENV LOG_DIR "$APP_DIR/log"
ENV SRC_DIR "$APP_DIR/src"
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get -y install apt-utils && \
    apt-get -y install \
        cron \
        curl \
        iputils-ping \
        iproute2 \
        logrotate \
        redis-server \
        python \
        python-pip \
        rsyslog \
        ssh \
        tcpdump 

# ensure required directories always exists within container even before bind mount
RUN mkdir -p $LOG_DIR && \
    mkdir -p $DATA_DIR && \
    mkdir -p $LOCAL_DATA_DIR && \
    mkdir -p $SRC_DIR && \
    mkdir -p $SRC_DIR/Service && \
    mkdir -p $SRC_DIR/UIAssets

# setup redis which only requires copying over config file
COPY ./conf/redis.conf /etc/redis/redis.conf
RUN chmod 777 $LOG_DIR && \
    chmod 640 /etc/redis/redis.conf && \
    chown redis:redis /etc/redis/redis.conf

# install and configure apache
RUN apt-get -y install \
        apache2 \
        libapache2-mod-wsgi
COPY ./conf/apache2-000-default.conf /etc/apache2/sites-available/000-default.conf
COPY ./conf/apache2-default-ssl.conf /etc/apache2/sites-available/default-ssl.conf
RUN mkdir -p $LOG_DIR/apache2 && \
    chown www-data:www-data $LOG_DIR/apache2 && \
    /usr/sbin/a2enmod ssl && \
    /usr/sbin/a2dissite 000-default && \
    /usr/sbin/a2dissite default-ssl && \
    /usr/sbin/a2ensite 000-default && \
    /usr/sbin/a2ensite default-ssl

# install and configure mongodb 3.6
RUN apt-get install -y apt-transport-https && \
        apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 2930ADAE8CAF5059EE73BB4B58712A2291FA4AD5 && \
        echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu xenial/mongodb-org/3.6 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-3.6.list && \
        apt-get update && \
        apt-get install -y mongodb-org
COPY ./conf/mongodb-init.d /etc/init.d/mongodb
COPY ./conf/mongod.conf /etc/mongod.conf
RUN chmod 755 /etc/init.d/mongodb && \
    mkdir -p $LOG_DIR/mongo && \
    mkdir -p $DATA_DIR/db && \
    mkdir -p $LOCAL_DATA_DIR/db && \
    chown mongodb:mongodb $LOG_DIR/mongo && \
    chown mongodb:mongodb $DATA_DIR/db && \
    chown mongodb:mongodb $LOCAL_DATA_DIR/db

# setup logrotate for minute granularity and add custom logging directories
RUN mkdir -p /etc/cron.minute && \
    chmod 755 /etc/cron.minute
COPY ./conf/crontab /etc/crontab
COPY ./conf/cron.minute.logrotate /etc/cron.minute/logrotate
COPY ./conf/logrotate.d.app /etc/logrotate.d/app
RUN chmod 644 /etc/logrotate.d/app && \
    chmod 755 /etc/cron.minute/logrotate && \
    chmod 600 /etc/crontab

# upgrade pip
RUN pip install --upgrade pip

# copy python requirements and install
# pull backend source and install requirements
COPY ./requirements.txt $SRC_DIR/Service/
RUN pip install -r $SRC_DIR/Service/requirements.txt

WORKDIR $SRC_DIR
CMD $SRC_DIR/start.sh
