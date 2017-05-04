#!/bin/bash

startDir="`pwd`"
### app settings required for setup
appGitUrl="https://github.com/agccie/ACI-EnhancedEndpointTracker.git"
appName="eptracker"
appLogDir="/var/log/ept/"
### install settings required for apache setup
installDir="/var/www/$appName/"
installLog="$startDir/setup.log"
installUser=`who am i | awk '{print $1}'`
firstRun="/home/$installUser/firstRun.sh"

# ensure user is running setup as root
if [ "$(whoami)" != "root" ]; then
    echo "Sorry, you are not root."
    exit 1
fi

install_apache()
{

    # install apache and push default configuration (enabling SSL as well)
    # RESTRICTIONS on new apache that all services must be installed at /var/www
    # THEREFORE, this project will be installed at /var/www/$appName

    sudo apt-get install apache2 -y
    sudo apt-get install libapache2-mod-wsgi -y
    sudo a2enmod ssl
    sudo chown $installUser:www-data ./app.wsgi
    sudo chmod 775 ./app.wsgi

    # apache default site
    echo "
<VirtualHost *:80>
    WSGIDaemonProcess $appName user=$installUser group=www-data threads=5
    WSGIScriptAlias / $installDir/app.wsgi

    <Directory $installDir>
        WSGIProcessGroup %{GLOBAL}
        WSGIApplicationGroup %{GLOBAL}
        Order deny,allow
        Allow from all
    </Directory>
    ErrorLog \${APACHE_LOG_DIR}/error.log
    CustomLog \${APACHE_LOG_DIR}/access.log combined
</VirtualHost>
# vim: syntax=apache ts=4 sw=4 sts=4 sr noet
" > /etc/apache2/sites-available/000-default.conf

    # apache SSL site
    ssl="_ssl"
    appName_ssl=$appName$ssl
    echo "
<IfModule mod_ssl.c>
    <VirtualHost _default_:443>
        WSGIDaemonProcess $appName_ssl user=$installUser group=www-data threads=5
        WSGIScriptAlias / $installDir/app.wsgi
        <Directory $installDir>
            WSGIProcessGroup %{GLOBAL}
            WSGIApplicationGroup %{GLOBAL}
            Order deny,allow
            Allow from all
        </Directory>
        ErrorLog \${APACHE_LOG_DIR}/error.log
        CustomLog \${APACHE_LOG_DIR}/access.log combined
        #Include conf-available/serve-cgi-bin.conf
        SSLEngine on
        SSLCertificateFile  /etc/ssl/certs/ssl-cert-snakeoil.pem
        SSLCertificateKeyFile /etc/ssl/private/ssl-cert-snakeoil.key
        #SSLCertificateChainFile /etc/apache2/ssl.crt/server-ca.crt
        #SSLCACertificatePath /etc/ssl/certs/
        #SSLCACertificateFile /etc/apache2/ssl.crt/ca-bundle.crt
        #SSLCARevocationPath /etc/apache2/ssl.crl/
        #SSLCARevocationFile /etc/apache2/ssl.crl/ca-bundle.crl
        #SSLVerifyClient require
        #SSLVerifyDepth  10
        #SSLOptions +FakeBasicAuth +ExportCertData +StrictRequire
        <FilesMatch \"\.(cgi|shtml|phtml|php)$\">
                SSLOptions +StdEnvVars
        </FilesMatch>
        <Directory /usr/lib/cgi-bin>
                SSLOptions +StdEnvVars
        </Directory>
        BrowserMatch \"MSIE [2-6]\" \
                nokeepalive ssl-unclean-shutdown \
                downgrade-1.0 force-response-1.0
        # MSIE 7 and newer should be able to use keepalive
        BrowserMatch \"MSIE [17-9]\" ssl-unclean-shutdown
    </VirtualHost>
</IfModule>
# vim: syntax=apache ts=4 sw=4 sts=4 sr noet
" > /etc/apache2/sites-available/default-ssl.conf
    
    sudo a2dissite 000-default
    sudo a2dissite default-ssl
    sudo a2ensite 000-default
    sudo a2ensite default-ssl
    sudo service apache2 restart
}

install_mongodb()
{
    # ubuntu distribution (16.04+) should maintain a working mongdb
    sudo apt-get install -y mongodb 
}

install_exim4()
{
    # install exim4 and configure 
    apt-get install -y exim4
    sed -i -e "s/dc_eximconfig_configtype.*/dc_eximconfig_configtype='internet'/g" /etc/exim4/update-exim4.conf.conf
    service exim4 restart
}

install()
{
    # install project dependences
    apt-get update >> $installLog 2>&1
    echo -n "."
    apt-get install -y git vim >> $installLog 2>&1
    echo -n "."
    apt-get install -y python python-dev python-pip libffi-dev libssl-dev python-pip >> $installLog 2>&1
    echo -n "."

    # some werid pip problems on current ubuntu pip - easy install with upgrade fixes it
    easy_install -U pip >> $installLog 2>&1

    # create directory and pull code
    mkdir $installDir -p >> $installLog 2>&1
    cd $installDir >> $installLog 2>&1
    export GIT_SSL_NO_VERIFY=true
    git clone $appGitUrl .  >> $installLog 2>&1
    echo -n "."

    # install pip requirements
    pip install -r requirements.txt --allow-all-external >> $installLog 2>&1
    echo -n "."
    
    install_apache >> $installLog 2>&1
    echo -n "."
    install_mongodb  >> $installLog 2>&1
    echo -n "."
    install_exim4  >> $installLog 2>&1
    echo -n "."
    sudo apt-get install ntp -y >> $installLog 2>&1
    echo -n "."

    # setup logging directory
    mkdir $appLogDir -p >> $installLog 2>&1
    chown $installUser:www-data $appLogDir >> $installLog 2>&1
    chmod 777 $appLogDir >> $installLog 2>&1
    touch $appLogDir/ept.log >> $installLog 2>&1
    touch $appLogDir/utils.log >> $installLog 2>&1
    chmod 777 $appLogDir/* >> $installLog 2>&1
    chown $installUser:www-data $appLogDir/* >> $installLog 2>&1
    echo -n "."

    # ensure permissions are still correct for installDir
    chown $installUser:www-data $installDir -R >> $installLog 2>&1
    chmod 775 $installDir -R >> $installLog 2>&1
    echo -n "."
}

display_complete()
{
echo "
Install Completed. Please see $installLog for more details. Reload the
machine before using this application.

After reload, first time user should run the firstRun.sh script 
in $installUser's home directory:
    sudo $firstRun
"
}

create_firstRun()
{
    # create firstRun.sh script in user directory
    echo '#!/bin/bash
    # ensure user is running setup as root
    if [ "$(whoami)" != "root" ]; then
        echo "Sorry, you are not root."
        exit 1
    fi' > $firstRun
    echo "
    echo \"\"
    echo \"Setting up system\"
    $installDir/bash/setup_system.sh
    echo \"Done\"
    echo \"\"
    echo \"Setting up application\"

    # ensure app.wsgi is present for apache2
    cp $installDir/aci_app_store/Service/app.wsgi $installDir/app.wsgi
    python $installDir/setup_db.py --no_verify
    chown $installUser:www-data $installDir/app.wsgi
    chmod 777 $appLogDir/*
    sudo service apache2 restart

    # ensure proper environment variables are set for this VM
    mkdir -p $installDir/instance
    echo \"\" > $installDir/instance/config.py
    echo \"LOG_DIR=\\\"$appLogDir\\\"\" >> $installDir/instance/config.py
    echo \"LOG_ROTATE=0\" >> $installDir/instance/config.py
    echo \"EMAIL_SENDER=\\\"noreply@eptracker.app\\\"\" >> $installDir/instance/config.py
    " >> $firstRun
    echo '
    
    # guess IP
    pintf=`ifconfig | egrep Ethernet | awk '{print $1}' | head -1`
    thisIp=`ifconfig $pintf | egrep -o "inet addr:[0-9\.]+" | egrep -o "[0-9\.]+"`
    if [[ $thisIp =~ ^[0-9\.]+ ]] ; then
        echo "
        Setup has completed! 
        You can now login to the web interface with username \"admin\" and the 
        password you just configured at:
            https://$thisIp/

        
        It is recommended to reload the VM before proceeding."' >> $firstRun
    echo "
        $installDir/bash/setup_system.sh -r 
        " >> $firstRun
    echo '
    else
        echo "
        Setup has completed!

        ERROR, unable to determine $pintf IP address. Either dhcp process failed
        or one or more networking settings are incorrect. Please verify the network 
        configuration along with any errors in the follow files:
            sudo vim /etc/networking/interfaces
            cat /var/log/syslog | egrep networking
        Once the configuration has been corrected, restart the networking process via:
            sudo service networking restart
        Verify an IP address is assigned to $pintf via:
            ifconfig $pintf

        Once an IP address is assigned, you can login to the web interface with username
        \"admin\" and the password you configured above at:
            https://<this-host-ip-address>/
        "
    fi
    ' >> $firstRun
    
        
    chmod 755 $firstRun
    
}

#-----------------------------------------------------------------
# MAIN
if [[ "$1" == "--install" ]]; then
    # force argument to prevent accidentally running install
    echo -n "Installing ."
    install
    echo ""
    display_complete
    create_firstRun
    cd $startDir
elif [[ "$1" == "--firstRun" ]]; then
    # just run firstRun script
    echo "Building firstRun script"
    create_firstRun
    cd $startDir
else
    # no option provided, prompt user
    echo "Usage: ./setup.sh {args}"
    echo "  --install   Run full install"
    echo "  --firstRun  Create firstRun script"
    exit 0
fi
