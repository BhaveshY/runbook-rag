---
title: Pod Lifecycle
---

This page describes the lifecycle of a Pod. Pods follow a defined lifecycle, starting in the
`Pending` phase, moving through `Running` if at least one of its primary containers starts OK.

## Container probes

### livenessProbe

Indicates whether the container is running. If the liveness probe fails, the kubelet kills the container,
and the container is subjected to its restart policy. If a container does not provide a liveness probe,
the default state is `Success`.

### readinessProbe {#readiness-probe}

Indicates whether the container is ready to respond to requests. If the readiness probe fails, the
EndpointSlice controller removes the Pod's IP address from the EndpointSlices of all Services that match the Pod.

## Restart policy

The `spec` of a Pod has a `restartPolicy` field with possible values Always, OnFailure, and Never.
After containers in a Pod exit, the kubelet restarts them with an exponential backoff delay (10s, 20s, 40s, …), that is capped at 300 seconds.
