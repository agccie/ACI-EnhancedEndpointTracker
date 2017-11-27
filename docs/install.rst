Install
=======

The application can be installed directly on the APIC or configured to as a 
standalone application.

ACI Application
^^^^^^^^^^^^^^^

The most recent public release can be downloaded from `ACI AppCenter <https://aciappcenter.cisco.com/enhancedendpointtracker-2-2-1n.html>`_.  If you need to build the application from source, use the procedure below.

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

TODO
