The Enhanced Endpoint Tracker maintains a database of endpoint events on a per-node basis allowing for unique fabric-wide analysis.  The application can be configured to analyze, notify, and automatically remediate various endpoint events.  This gives ACI fabric operators better visibility and control over the endpoints in the fabric.

Features include:

1.    Easy to use GUI for viewing endpoint state and events within the fabric
2.    Per-node event history for each endpoint in the fabric.  This allows administers to quickly verify that each node in the fabric has learned an endpoint correctly
3.    Analysis and Notifications for the following events:
    a.    Endpoint move
    b.    Off-subnet learns
    c.    Stale endpoint 
4.    Notifications can be sent via syslog and email
5.    Automatically clear off-subnet endpoints
6.    Automatically clear stale endpoints 
7.    Manually clear an endpoint through the GUI on user-selected nodes

For more details, refer to the online documentation at:
http://aci-enhancedendpointtracker.readthedocs.io/en/latest/


