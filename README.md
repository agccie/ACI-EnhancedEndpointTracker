# EnhancedEndpointTracker

| :exclamation: This application is no longer being developed or tested with new ACI releases. |
|----------------------------------------------------------------------------------------------|

The EnhancedEndpointTracker is a Cisco ACI application that maintains a database of endpoint
events on a per-node basis allowing for unique fabric-wide analysis. The application can be
configured to analyze, notify, and automatically remediate various endpoint events. This gives
ACI fabric operators better visibility and control over the endpoints in the fabric.

Features include:

- Easy to use GUI with fast type-ahead search for any mac/ipv4/ipv6 endpoint in the fabric
- Move, offsubnet, rapid, and stale endpoint analysis
- Configurable notification options via syslog/email for various events detected by the app
- Capability to clear an endpoint on one or more nodes via GUI or API
- Distributed architecture allowing app to grow based on the size of the fabric
- Fully documented swagger API to allow for easy integration with other tools.

This application is written in python and utilizes a distributed MongoDB database to persist data.
It also relies on a custom Flask framework for handling API requests, Redis for messaging between
components, and Angular with CiscoUI for the frontend.

For more details, refer to the online documentation at:
http://aci-enhancedendpointtracker.readthedocs.io/en/latest/ (http://aci-enhancedendpointtracker.readthedocs.io/en/latest/)
