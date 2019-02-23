Introduction
============

.. raw:: html

    <div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; height: auto;">
        <iframe width="1280" height="720" src="https://www.youtube.com/embed/HIisSTBr-bw" frameborder="0" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
    </div>

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

