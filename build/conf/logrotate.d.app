#
# Global options
#

su root root
copytruncate
compress
notifempty
missingok
dateext
dateformat -%Y%m%d-%s
size 5M
rotate 10

/home/app/log/apache2/*.log {
    delaycompress
    sharedscripts
    postrotate
        if /etc/init.d/apache2 status > /dev/null ; then
            /etc/init.d/apache2 reload > /dev/null;
        fi;
    endscript
}
/home/app/log/mongo/*.log {
    delaycompress
}
/home/app/log/mongo/*/*.log {
    delaycompress
}
/home/app/log/*.log {
    size 50M
}
