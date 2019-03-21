.. _releases:

Releases
========

This page will track information about each new release along with new features and any known
issues. 

Version 2.1.1
-------------

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


