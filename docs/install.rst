Install
=======

The ACI EnhancedEndpointTracker can be installed directly on the APIC as an ACI app or deployed as
a standalone application hosted on a baremetal or virtual machine.

ACI Application
---------------

The application can be deployed on the APIC. There are two modes supported, both available on 
`ACI Appcenter <https://aciappcenter.cisco.com>`_.

* `mini <https://aciappcenter.cisco.com/enhancedendpointtrackermini-2-2-1n.html>`_ is backwards 
  compatible with APIC 2.x and 3.x. However, there are memory constraints that limit the supported 
  scale

* `full <https://aciappcenter.cisco.com/enhancedendpointtracker-4-0-1g.html>`_ scale application 
  supported on APIC 4.x and above.

After downloading the app, follow the directions for uploading and installing the app on the APIC:

* `2.x Install Video Example <https://www.cisco.com/c/en/us/td/docs/switches/datacenter/aci/apic/sw/2-x/App_Center/video/cisco_aci_app_center_overview.html>`_
* `2.x Install Instructions <https://www.cisco.com/c/en/us/td/docs/switches/datacenter/aci/apic/sw/2-x/App_Center/developer_guide/b_Cisco_ACI_App_Center_Developer_Guide/b_Cisco_ACI_App_Center_Developer_Guide_chapter_0110.html#d7964e613a1635>`_
* `3.x Install Instructions <https://www.cisco.com/c/en/us/td/docs/switches/datacenter/aci/apic/sw/2-x/App_Center/developer_guide/b_Cisco_ACI_App_Center_Developer_Guide/b_Cisco_ACI_App_Center_Developer_Guide_chapter_0110.html#d11320e725a1635>`_ 

In you are executing the ``mini`` app, the APIC will enforce a **2G** memory limit and a **10G** 
disk quota.  As a result, it may crash if there are a large number of endpoints or high number 
events per second. As a best practice, it is recommended to deploy in ``full`` mode or 
``standalone`` mode if the total number of per-node endpoints exceeds ``32k``.  You can determine 
the per-node endpoint count via the following moquery on the APIC:

.. code-block:: bash

    apic# moquery -c epmDb -x query-target=subtree -x target-subtree-class=epmIpEp,epmMacEp,epmRsMacEpToIpEpAtt -x rsp-subtree-include=count

If the running ``mini`` mode and it is exceeding the memory limits, you may see the symptoms below:

* Consistent monitor restarts due to "subscriber no longer running"
* Monitor restart due to "worker 'w0' not longer active"
* Monitor stuck or restarting during "getting initial endpoint state"

Standalone Application
----------------------
The ``standalone`` app is one that runs on a dedicated host/VM and makes remote connections to the 
APIC opposed to running as a container on the APIC.  For large scale fabrics or development 
purposes, standalone is the recommended mode to run this application.  The standalone app also has 
a few different deployment options:

* ``all-in-one`` is a single container with all required processes running.  This is similar to 
  ``mini`` mode executing on the APIC, however the memory and compute restrictions are based on the 
  host device and therefore can support much larger scale. This is the easiest way to deploy the 
  app as it can be started with a single command.

* ``cluster`` uses a distributed architecture to execute multiple container across one or more 
  nodes. This allows the app to scale with the size of the fabric. This is similar to the ``full`` 
  mode executing on the APIC but can be deployed in any custom environment that supports container 
  orchestration. 

All-in-One Mode
^^^^^^^^^^^^^^^

To execute in ``all-in-one`` mode, you need a host with docker installed.  See the 
`Docker documentation <https://docs.docker.com/install/>`_ for installing docker on your host.  
Once installed, execute the following command to download the EnhancedEndpointTracker docker image 
and run it:

.. code-block:: bash

    host$ docker run --name ept -p 5000:443 -d agccie/enhancedendpointtracker:latest

The command will start an instance of EnhancedEndpointTracker with the web server running on port 
5000. Login to the web UI at `https://localhost:5000 <https://localhost:5000>`_.  See the usage 
section for further details regarding how to use the app.

Cluster Mode
^^^^^^^^^^^^

The EnhancedEndpointTracker app can be deployed in a distributed cluster. Users can deploy in their 
own cluster or use a `prebuilt OVA <https://cisco.app.box.com/s/6us23gzr8nwplrmtjmpp5xaos1wywa22>`_.  
This section will focus on the OVA.

The recommended sizing for the VM is as follows:
   * 8 vCPU
   * 16G memory
   * 75G harddisk, thick provisioned

The OVA contains the following components preinstalled:

* Docker CE 18.09.02
* Python 2.7
* Ntp
* Network manager 
* EnhancedEndpointTracker docker image specific to the version of the OVA 
* A copy of the EnhancedEndpointTracker 
  `source code <https://github.com/agccie/ACI-EnhancedEndpointTracker>`_ located in 
  */opt/cisco/src* directory

Once the OVA is deployed, access the console with the credentials below. Note, you will be required 
to change the password on first login.

* username: **eptracker**
* password: **cisco**

To get started with the OVA, perform the following steps:

  * Configure host networking and hostname
  * (Optional) Configure NTP
  * Configure the cluster and deploy the stack
  * Manage the app via the web GUI

If you are deploying the cluster with more than one node, ensure there is connectivity between each 
node in the cluster and the following ports are allowed:

  * **TCP** port **2377** for cluster management
  * **TCP** and **UDP** port **7046** for communication between nodes
  * **UDP** port **4789** for overlay traffic
  * **TCP** port **22** for auto-deployment and setup

Configure VM Networking
~~~~~~~~~~~~~~~~~~~~~~~

The OVA is simply a Ubuntu 18.04 install. Users can use any mechanism they prefer to initialize the 
network.  The example below uses network manager TUI which is preinstalled on the VM.

* Enter **sudo nmtui**
* Choose 'Edit a connection' 

|standalone-console-nmtui-p1|

* Edit the appropriate connection. By default, the connection type is likely **Automatic** (DHCP) 
  but if you need to set a static IP address you will need to change the mode to **Manual** and the 
  set the appropriate info.

|standalone-console-nmtui-p3|

|standalone-console-nmtui-p4|

* To apply the updated configuration, you will need to deactivate and then activate the configured 
  interface.

|standalone-console-nmtui-p5|

|standalone-console-nmtui-p6|

* Ensure you also set the hostname for the VM.  You will need to logout and log back in to see the 
  hostname updated.

|standalone-console-nmtui-p8|

|standalone-console-nmtui-p9|

(Optional) Configure NTP
~~~~~~~~~~~~~~~~~~~~~~~~

All timestamps for the app are based on the timestamp of the server itself.  If you are running the 
app on a cluster with more than 1 VM or if the time on the VM is unreliable, then timestamps for 
events and analysis may be incorrect.  You can use **ntpd** to configure ntp servers on the host.

* Use vim or your favorite editor to set the required NTP servers under */etc/ntp.conf*

  .. code-block:: bash

      eptracker@ept-node1$ sudo vim /etc/ntp.conf

* Add each ntp server to the end of the file and save the results.  For example:

  .. code-block:: bash

      eptracker@ept-node1$ cat /etc/ntp.conf | egrep "^server"
      server 172.18.108.15
      server 172.18.108.14

* Restart the ntp process and validate the configuration was successful. **Note**, it may take 
  several minutes before ntp synchronizes the clock:

  .. code-block:: bash

      eptracker@ept-node1:~$ sudo service ntp restart
      eptracker@ept-node1:~$ ntpq -p
           remote           refid      st t when poll reach   delay   offset  jitter
      ==============================================================================
      calo-timeserver .XFAC.          16 u    - 1024    0    0.000    0.000   0.000
      calo-timeserver .XFAC.          16 u  27h 1024    0    0.000    0.000   0.000

      eptracker@ept-node1:~$ timedatectl status
                            Local time: Mon 2019-02-18 02:42:33 UTC
                        Universal time: Mon 2019-02-18 02:42:33 UTC
                              RTC time: Mon 2019-02-18 02:42:33
                             Time zone: Etc/UTC (UTC, +0000)
             System clock synchronized: yes
      systemd-timesyncd.service active: yes  <--------- synchronized
                       RTC in local TZ: no


Configure the cluster and deploy the stack
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``cluster`` mode with the OVA uses docker swarm for the overlay and network orchestration. Even if 
there is only a single node, the swarm needs to be configured.  This can be done manually or via 
scripts already available on the VM. Before starting, ensure that networking has been configured on 
all nodes and they are able to communicate on the ports previously listed. The high level process 
for deploying the swarm is as follows:

* Configure the VM as a swarm leader
* Export the manager token to all other nodes and add them to the swarm
* Add a label called ‘node’ with the appropriate node number to each node in the cluster. The 
  docker compose file uses the node labels to ensure the db shards and replicas are properly 
  distributed.
* Create the docker compose file based on the desired number of shards, replicas, and workers 
  distributed across the cluster nodes.
* Deploy the stack.

All containers deployed in the stack rely on the ``agccie/enhancedendpointtracker:<version>`` 
container. This is available on docker hub and is also available pre-installed on the OVA. There is 
no internet requirement to get the app deployed on the OVA.

There is a script already available on the OVA to assist with the deployment. Before executing the 
script, ensure that you have set the desired number of workers, db shard and replica count along
with memory limits. The defaults are sufficient for most setups:

``/opt/cisco/src/cluster/swarm/swarm_config.yml``

  .. code-block:: bash

      # app configuration (note, this is specific to container bring up, majority of app config is
      # available within the app UI)
      app:
          # application service name
          name: "ept"
          # external ports for http and https.  Set to '0' to disable it.
          http_port: 80
          https_port: 443
          # number of workers containers
          workers: 10
          # internal network for communication between app components. This subnet should only be changed
          # if it overlaps with an existing network
          subnet: "192.0.2.0/24"
      
      # mongodb cluster configuration
      database:
          # shards is the number of db shards.
          #
          # replicas are per-shard.  A replica count of 1 has no redundancy. Recommended replica count
          # is 3 for full redundancy.  Note, the replica count must be <= total nodes configured in the
          # cluster.
          #
          # memory is a float measured in GB and is a per shard/per replica limit.
          # The aggregate memory of all containers running on a single node should be less than total
          # memory on the node or the db may crash.
          shardsvr:
              shards: 3
              replicas: 3
              memory: 2.0
      
          # configsvr holds meta data for db shards.  The replica count here is per configsrv service.
          # Again, the number of replicas should be less than or equal to the number of nodes.
          #
          # memory is a float measured in GB and is per instance
          configsvr:
              replicas: 3
              memory: 2.0 
 
To automatically configure the swarm and deploy the service, use the ``app-deploy`` script. The 
example below assumes a 3-node cluster.

  .. code-block:: bash

      eptracker@ept-node1:~$ app-deploy --deploy
      Number of nodes in cluster [1]: 3
      UTC 2019-02-16 23:38:25.229||INFO||loading config file: /opt/cisco/src/cluster/swarm/swarm_config.yml
      UTC 2019-02-16 23:38:25.318||INFO||compose file complete: /tmp/compose.yml
      UTC 2019-02-16 23:38:25.421||INFO||initializing swarm master
       
      Enter hostname/ip address for node 2: 192.168.4.112  <--- you will be prompted for each node IP
      Enter hostname/ip address for node 3: 192.168.4.113

      Enter ssh username: eptracker   <------ you will be prompted for ssh username/password
      Enter ssh password:

      UTC 2019-02-16 23:38:37.340||INFO||Adding worker to cluster (id:2, hostname:192.168.4.112)
      UTC 2019-02-16 23:38:46.400||INFO||Adding worker to cluster (id:3, hostname:192.168.4.113)
      UTC 2019-02-16 23:38:49.547||INFO||docker cluster initialized with 3 node(s)
      UTC 2019-02-16 23:38:49.548||INFO||deploying app services, please wait...
      UTC 2019-02-16 23:46:58.994||INFO||3 services pending, re-check in 60.0 seconds
      UTC 2019-02-16 23:47:59.162||INFO||app services deployed
      UTC 2019-02-16 23:48:14.168||INFO||deployment complete

.. note:: The ``app-deploy`` script requires that all nodes in the cluster have the same 
          username/password configured.  Once the deployment is complete, you can set unique 
          credentials on each node.

Manager the App via the web-GUI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After deployment is complete, open a web browser to the IP address of any node in the cluster. Using
the example above we could access the app on node-3 via to https://192.168.4.113/. The app can be 
fully managed from the UI. See the usage section for further details regarding how to use the app.



.. |standalone-console-nmtui-p1| image:: imgs/standalone-console-nmtui-p1.png
   :align: middle

.. |standalone-console-nmtui-p2| image:: imgs/standalone-console-nmtui-p2.png
   :align: middle

.. |standalone-console-nmtui-p3| image:: imgs/standalone-console-nmtui-p3.png
   :align: middle

.. |standalone-console-nmtui-p4| image:: imgs/standalone-console-nmtui-p4.png
   :align: middle

.. |standalone-console-nmtui-p5| image:: imgs/standalone-console-nmtui-p5.png
   :align: middle

.. |standalone-console-nmtui-p6| image:: imgs/standalone-console-nmtui-p6.png
   :align: middle

.. |standalone-console-nmtui-p8| image:: imgs/standalone-console-nmtui-p8.png
   :align: middle

.. |standalone-console-nmtui-p9| image:: imgs/standalone-console-nmtui-p9.png
   :align: middle
