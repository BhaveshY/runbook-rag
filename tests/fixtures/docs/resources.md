---
title: Resource Management for Pods and Containers
---

When you specify a Pod, you can optionally specify how much of each resource a container needs.
The most common resources to specify are CPU and memory (RAM); there are others.

## CPU limits

CPU limits are enforced by CPU throttling. When a container approaches its CPU limit, the kernel
will restrict access to the CPU corresponding to the container's limit. Thus, a CPU limit is a hard
limit the kernel enforces. Containers may not use more CPU than is specified in their CPU limit.

## Memory limits

Memory limits are enforced by the kernel with out of memory (OOM) kills. When a container uses more
than its memory limit, the kernel may terminate it. If you specify a memory limit for a container
but do not specify a memory request, Kubernetes automatically assigns a memory request that matches the limit.
