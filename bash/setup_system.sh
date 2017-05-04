#!/bin/bash
username=`who am i | awk '{print $1}'`
ntpconfig="/etc/ntp.conf"
ifconfig="/etc/network/interfaces"
pintf=`ifconfig | egrep Ethernet | awk '{print $1}' | head -1`

# ensure user is running setup as root
if [ "$(whoami)" != "root" ]; then
    echo "Sorry, you are not root."
    exit 1
fi

confirmed="0"
confirm()
{
    local __input="$1"
    if [[ "$__input" == "" ]] ; then
        read -p "Please enter 'yes' or 'no': " user_in
        confirm "$user_in"
    elif [[ $__input =~ ^[yY]([eE]?[sS]?)? ]] ; then
        confirmed="1"
    else
        confirmed="0"
    fi
}

# configure ntp settings and disable any existing ntp servers
setup_ntp()
{
    echo ""
    echo "NTP is HIGHLY recommended to ensure event timestamps are accurate."
    read -p "Would you like to configure ntp? [yes/no] " user_in
    confirm "$user_in"
    if [ "$confirmed" == "0" ] ; then
        return
    fi
    # prompt user for 1 or more ntp servers and update /etc/ntp.conf
    read -p "Enter one or more ntp servers (separate by space): " servers
    read -p "Disable existing NTP servers? [yes/no] " user_in
    confirm "$user_in"
    if [ "$confirmed" == "1" ] ; then
            cat $ntpconfig | egrep '^[ ]*server [^ ]+' | while read s ; do 
                echo "Disabling existing ntp server [$s]"
                sed -i -e "s/$s/#$s/" $ntpconfig
            done
    fi
    # append new ntp servers to end of file
    for s in $(echo $servers | tr " " "\n") ; do
        echo "Adding new ntp server: [$s]"
        echo "server $s" >> $ntpconfig
    done

    # restart ntp 
    systemctl restart ntp

    echo ""
    echo "NTP have been configured. Use the following command to"
    echo "monitor clock synchronization: "
    echo "  ntpq -c lpeer"
    echo "  timedatectl status"
    echo ""
}

# configure current timezone
setup_tz()
{
    tz=`cat /etc/timezone`
    read -p "Update timezone[$tz]? [yes/no] " user_in
    confirm "$user_in"
    if [ "$confirmed" == "1" ] ; then
        sudo dpkg-reconfigure tzdata
    fi
}

setup_network()
{
    ipaddr=""
    netmask=""
    gateway=""
    domain=""
    nameServers=""
    read -p "Setup networking? [yes/no] " user_in
    confirm "$user_in"
    if [ "$confirmed" == "0" ] ; then
        return
    fi
    read -p "Use DHCP? [yes/no] " user_in
    confirm "$user_in"
    if [ "$confirmed" == "1" ] ; then
        echo "" > $ifconfig
        echo "source /etc/network/interfaces.d/*" >> $ifconfig
        echo "" >> $ifconfig
        echo "auto lo" >> $ifconfig
        echo "iface lo inet loopback" >> $ifconfig
        echo "" >> $ifconfig
        echo "auto $pintf" >> $ifconfig
        echo "iface $pintf inet dhcp" >> $ifconfig
    else
        while [[ 1 ]] ; do
            read -p "  IP Address             : " ipaddr
            read -p "  Subnet Mask            : " netmask
            read -p "  Default Gateway        : " gateway
            read -p "  DNS Server(s)          : " nameServers
            read -p "  Domain (i.e. cisco.com): " domain 
            echo ""
            echo "Confirm Settings"
            echo "  IP Address     : $ipaddr"
            echo "  Subnet Mask    : $netmask"
            echo "  Default Gateway: $gateway"
            echo "  DNS Server(s)  : $nameServers"
            echo "  Domain         : $domain"
            read -p "Accept [yes/no] " user_in
            confirm "$user_in"
            if [ "$confirmed" == "1" ] ; then
                break
            fi
        done
        echo "" > $ifconfig
        echo "source /etc/network/interfaces.d/*" >> $ifconfig
        echo "" >> $ifconfig
        echo "auto lo" >> $ifconfig
        echo "iface lo inet loopback" >> $ifconfig
        echo "" >> $ifconfig
        echo "auto $pintf" >> $ifconfig
        echo "iface $pintf inet static" >> $ifconfig
        
        if [[ $ipaddr =~ [0-9\.]+ ]] ; then
            echo "  address $ipaddr"  >> $ifconfig
        fi
        if [[ $netmask =~ [0-9\.]+ ]] ; then
            echo "  netmask $netmask" >> $ifconfig
        fi
        if [[ $gateway =~ [0-9\.]+ ]] ; then
            echo "  gateway $gateway" >> $ifconfig
        fi
        if [[ $nameServers =~ [a-zA-Z0-9\.]+ ]] ; then
            echo "  dns-nameservers $nameServers" >> $ifconfig
        fi
        if [[ $domain =~ [a-zA-Z0-9\.]+ ]] ; then
            echo "  dns-search $domain" >> $ifconfig
        fi
    fi
    echo "Networking settings have been updated!"
    echo "You can verify network configuration in $ifconfig"
    echo ""
    echo "restarting networking service... "
    sudo service networking restart
    
}

change_password()
{
    read -p "Update password for user '$username'? [yes/no] " user_in
    confirm "$user_in"
    if [ "$confirmed" == "1" ] ; then
        passwd $username
    fi
}

confirm_reload()
{
    read -p "        Reload now? [yes/no ] " user_in
    confirm "$user_in"
    if [ "$confirmed" == "1" ] ; then
        echo "Reloading ..."
        shutdown now -r
    fi
}

if [ "$1" == "-r" ]; then
    # reload with confirm option
    confirm_reload
else
    # normal setup functions
    change_password
    setup_network
    setup_tz
    setup_ntp
fi
