---
title: Images
content_type: concept
weight: 10
---

<!-- overview -->
A container image represents binary data that encapsulates an application and all its
software dependencies. Container images are executable software bundles that can run
standalone and that make very well defined assumptions about their runtime environment.

## Image pull policy

The `imagePullPolicy` for a container and the tag of the image affect when the
{{< glossary_tooltip text="kubelet" term_id="kubelet" >}} attempts to pull (download) the specified image.
The value is always set when the object is first _created_, and is not updated if the image's tag or digest later changes.

## ImagePullBackOff

The status `ImagePullBackOff` means that a container could not start because Kubernetes could not pull a container image
(for reasons such as invalid image name, or pulling from a private registry without `imagePullSecret`).
The `BackOff` part indicates that Kubernetes will keep trying to pull the image, with an increasing back-off delay.

```shell
kubectl describe pod POD_NAME
## this line is inside a code fence and is not a heading
```

See [the pod lifecycle](/docs/concepts/workloads/pods/pod-lifecycle/) for container states.
