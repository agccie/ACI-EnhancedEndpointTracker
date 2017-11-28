Install
=======

The application can be installed directly on the APIC or configured to as a 
standalone application.

ACI Application
^^^^^^^^^^^^^^^

The most recent public release can be downloaded from `ACI AppCenter <https://aciappcenter.cisco.com/enhancedendpointtracker-2-2-1n.html>`_.  After downloading the app, follow the directions for uploading and installing the app on the APIC:

* `2.x Install Video Example <https://www.cisco.com/c/en/us/td/docs/switches/datacenter/aci/apic/sw/2-x/App_Center/video/cisco_aci_app_center_overview.html>`_
* `2.x Install Instructions <https://www.cisco.com/c/en/us/td/docs/switches/datacenter/aci/apic/sw/2-x/App_Center/developer_guide/b_Cisco_ACI_App_Center_Developer_Guide/b_Cisco_ACI_App_Center_Developer_Guide_chapter_0110.html#d11320e518a1635>`_
* `3.x Install Instructions <https://www.cisco.com/c/en/us/td/docs/switches/datacenter/aci/apic/sw/2-x/App_Center/developer_guide/b_Cisco_ACI_App_Center_Developer_Guide/b_Cisco_ACI_App_Center_Developer_Guide_chapter_0110.html#d11320e725a1635>`_

If you need to build the application from source, use the procedure below.

Building ACI Application
""""""""""""""""""""""""

To build the application you'll need a development environment with git, python2.7, zip, and docker installed. 

.. warning:: Build process does not currently work on MAC OS due to incompatibility with sed program.
   It has successfully been performed on Ubuntu 16.04 and will likely work on other linux OS.

.. code-block:: bash

   # install via apt-get, yum, dnf, etc...
   root@ept-dev:~# apt-get install -y git python-pip zip

   # install docker
   root@ept-dev:~# curl -sSl https://get.docker.com/ | sh

   # download the source code  
   root@ept-dev:~# git clone https://github.com/agccie/ACI-EnhancedEndpointTracker
   root@ept-dev:~# cd ACI-EnhancedEndpointTracker

   # install package requirements
   root@ept-dev:~/ACI-EnhancedEndpointTracker# pip install aci_app_store/app_package/cisco_aci_app_packager-1.0.tgz

   # package application 
   root@ept-dev:~/ACI-EnhancedEndpointTracker# ./bash/build_app.sh
   root@ept-dev:~/ACI-EnhancedEndpointTracker# ls -al ~/ | grep aci
   -rw-r--r-- 1 root root    321062782 Nov 27 23:47 Cisco-EnhancedEndpointTracker-1.0.aci

.. note:: Docker is not required if the image file bundled within the app is
   available on the development environment. For example, you can install docker on a different 
   server, bundle the required docker image file, and then sftp/scp to the development server.

.. code-block:: bash

   # fetch the upstream docker image and copy to development server
   root@srv1:~# docker pull agccie/ept:latest
   root@srv1:~# docker save agccie/ept:latest | gzip -c > ~/my_docker_image.tgz
   root@srv1:~# scp ~/my_docker_iamge.tgz root@ept-dev:~/

   # package application with local docker image
   root@ept-dev:~/ACI-EnhancedEndpointTracker# ./bash/build_app.sh --img ~/my_docker_image.tgz
   UTC 2017-11-27 23:47:17.083     INFO         build.py:(84): creating required ACI app store directories
   UTC 2017-11-27 23:47:17.481     INFO         build.py:(225): packaging application
   UTC 2017-11-27 23:47:29.504     INFO         build.py:(236): packaged: ~/Cisco-EnhancedEndpointTracker-1.0.aci


Standalone Application
^^^^^^^^^^^^^^^^^^^^^^
The standalone application is one that runs on a dedicated host/VM and makes remote connections to the APIC opposed to running as a container on the APIC.  For large scale fabrics or development purposes, standalone is the recommended mode to run this application.

This application has primarily been developed and tested on Ubuntu host so that is recommended OS, however, any OS that supports the below requirements should work:

- Flask with Python2.7
- MongoDB
- A webserver that can host flask applications
- exim4 

  * exim4 is used only for sending email alerts via **mail** command. Alternative programs may also be used.

Easy Setup
""""""""""
The quickest way to get up and running is to spin up a host/VM/container and execute the install.sh script.  This will install and configure python, apache, mongo, exim4, along with appropriate python requirements, cron, ntp, and logrotate.  Additionally it will create a firstRun script that can be used to configure networking, ntp, and timezone for users unfamiliar with the OS.  Lastly, it will execute the initial db setup so the app is quickly up and running.

1.  Install Ubuntu Server 16.04 on a host or VM with the recommended minimal sizing:
  
   * 2 vCPU
   * 8G memory
   * 40G harddisk

2.  From the terminal, download and execute the install script.

.. code-block:: bash

   eptracker@ept-dev:~$ curl -sSl https://raw.githubusercontent.com/agccie/ACI-EnhancedEndpointTracker/master/bash/install.sh > install.sh
   eptracker@ept-dev:~$ chmod 777 install.sh
   eptracker@ept-dev:~$ sudo ./install.sh --install
   [sudo] password for eptracker:
   Installing ............

   Install Completed. Please see /home/eptracker/setup.log for more details. Reload the
   machine before using this application.

   After reload, first time user should run the firstRun.sh script
   in eptracker's home directory:
      sudo /home/eptracker/firstRun.sh

3.  After install, a firstRun script should be present in the install user's home directory.  Execute the firstRun script to configure the VM along with setting up the initial app database.

.. code-block:: bash

   # execute first-run
   eptracker@ept-dev:~$ sudo /home/eptracker/firstRun.sh
    
    Setting up system
    <snip>
    
    Setting up application
    Enter admin password:
    Re-enter password   :
    
            Setup has completed!
            You can now login to the web interface with username "admin" and the
            password you just configured at:
                https://192.168.5.231/
    
    
            It is recommended to reload the VM before proceeding.
            Reload now? [yes/no ] yes
    Reloading ...


4.  Now that the host/VM has all dependencies installed and configured and the database has been setup, access the VM web interface.

.. note:: The source code is available at /var/www/eptracker.  The apache module has been configured to service this directory.  Any change to the python source code may require both python worker and apache to be restarted.  

.. code-block:: bash

    eptracker@ept-dev:/var/www/eptracker$ ./bash/workers.sh -ka
    stopping all fabrics
    eptracker@ept-dev:/var/www/eptracker$ sudo service apache2 restart


Manual Setup
""""""""""""
TODO - (review the /bash/install.sh script for example on install python and all dependencies) 
