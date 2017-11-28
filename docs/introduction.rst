Introduction
============
The Enhanced Endpoint Tracker is a Cisco ACI application that maintains a database of endpoint events on a per-node basis allowing for unique fabric-wide analysis. The application can be configured to analyze, notify, and automatically remediate various endpoint events. This gives ACI fabric operators better visibility and control over the endpoints in the fabric.

Features include:

- Easy to use GUI for viewing endpoint state and events within the fabric
- Per-node event history for each endpoint in the fabric. This allows administers to quickly verify that each node in the fabric has learned an endpoint correctly
- Analysis and Notifications for the following events:

  * Endpoint move
  * Off-subnet learns
  * Stale endpoint

- Notifications can be sent via syslog and email
- Automatically clear off-subnet endpoints
- Automatically clear stale endpoints
- Manually clear an endpoint through the GUI on user-selected nodes
