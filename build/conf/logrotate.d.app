
/home/app/log/apache2/*.log {
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
/home/app/log/mongo/*.log {
       size 5M
       rotate 10
       copytruncate
       delaycompress
       compress
       notifempty
       missingok
}
/home/app/log/*.log {
       size 50M
       rotate 10
       copytruncate
       compress
       notifempty
       missingok
}
