.. _releases:

Releases
========

This page will track information about each new release along with new features and any known
issues. 

Version 2.1.2
-------------
*Released Aug 20 2019*

* fix for #46 fabricNode parsing broken on recent build breaks all eptNode tables
* update worker hash calculation for better load-balancing of work in scale setups
* use pub/sub redis messaging for broadcast between subscriber and workers
* reduce queue count and queue stat objects when using pub/sub broadcasts
* address timeouts on techsupport collection in multi-node standalone cluster
* reduce memory utilization on startup by streaming class queries
* include sort on all concrete objects initializations to prevent out-of-order results during paging
* use local user directory instead of global tmp for compose and deploy logs to prevent access
  problems for multiuser deployments
* additional user validation checks during docker swarm deployment
* increase manager timeout on app-status to support scale setups
* fix mongo cursor timeouts due to docker routed-mesh mongos load-balancing in multi-node standalone
  cluster
* propagate session/subscriber errors into fabric events so user can quickly isolate subscription
  restart errors
* added UI and backend support for configurable heartbeat interval, timeout, and retry count
* improve queue cleanup on fabric restart
* logrotate updates for apache logs
* UI polling service fix to prevent rapid requests on 400/500 errors
* UI optimize fabric status and manager polling mechanisms
* UI fix for cascading polling events on refresh

Version 2.1.1
-------------
*Released Mar 21 2019*

* Configurable SMTP settings including custom SMTP port, TLS encryption, and support for SMTP relay
  with optional authentication
* Configurable session timeout
* Configurable Refresh time for subscriptions. Staring in ACI 4.0 the subscription refresh time can 
  be extended up to 10 hours but will be limited to 60 seconds in older versions. The app will 
  auto-detect the version of code and apply a max of 60 seconds if APIC or switch is <4.0.
  Previously this was static at 30 seconds.
* Moved managed object event handling from subscriber process to dedicated worker. This addresses 
  issues such as high rate of tunnelIf events during initial build that can cause subscriber process 
  to hang.
* Cross reference fabricNode and topSystem to ensure inactive nodes are included in initial build. 
  This resolves a bug TEP calculation for vpcs if one node in the vpc is offline when app starts
* Disable accurate queue-length calculation on UI as it impacts manager process under scale
* Updates to app deployment scripts to allow user to pass in all arguments via command-line in 
  addition to editing cluster yaml file
* Trigger fabric restart on worker heartbeat failure and new worker detection
* Removed exim4 dependencies and rely on native python smtplib for email notifications


Version 2.0.x
-------------
*Released Feb 22 2019*

Initial 2.0 release. This was a complete rewrite with focus on scalability while maintaining and 
augmenting the feature set from the 1.x versions. Features include:

* Support for full endpoint scale fabric
* Easy to use GUI with fast type-ahead search for any mac/ipv4/ipv6 endpoint in the fabric
* Full details on current state of an endpoint in the fabric along with historical information
* Move, offsubnet, rapid, and stale endpoint analysis
* Configurable notification options via syslog/email for various events detected by the app
* Capability to clear an endpoint on one or more nodes via GUI or API
* Distributed architecture allowing app to grow based on the size of the fabric
* Fully documented swagger API to allow for easy integration with other tools
* Flexible deployment options include APIC and APIC-mini apps along with standalone all-in-one
  container and standalone docker-swarm cluster.


