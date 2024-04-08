# Taurus Cluster

Taurus is composed of 8 compute nodes each with 8xH100 GPU cards and 3 control plane nodes without GPU.

## Access

Taurus is operated via Kubernetes. Read the quick start of Nautilus (https://docs.nationalresearchplatform.org/userdocs/start/quickstart/) if you know nothing about Kubernetes.

You will get a config from the administrator. Put it into `~/.kube/config` or use

```bash
export KUBECONFIG=<path/to/config>
```

to set the current kubectl config for the terminal session.

### Example GPU pod

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-gpu-pod
spec:
  restartPolicy: Never
  containers:
  - name: cuda-container
    image: nvidia/cuda:12.1.1-base-ubuntu22.04
    args: ["sleep", "infinity"]
    resources:
      requests:
        cpu: 12
        memory: 32Gi
      limits:
        nvidia.com/gpu: 2
        cpu: 16
        memory: 32Gi
    volumeMounts:
      - name: taurusd
        mountPath: /taurusd
      - name: dshm
        mountPath: /dev/shm
  volumes:
    - name: taurusd
      persistentVolumeClaim:
        claimName: taurusd-pvc
    - name: dshm
      emptyDir:
        medium: Memory
```

### Cross-node Workload

RoCE discovery and configurations are yet to be figured out.

## Persistent Storage

The current storage is backed by WEKA, and can support high-performance small-file IO.
See the example GPU pod for mounting the storage.

The storage is exposed to the web via a S3 interface. You will get your access key and secret from the cluster admin.
The bucket `taurusd` is synchronized with the `/taurusd` mount shown in the GPU pod.
`rclone` is recommended to deal with S3. `rclone copy /local/file/or/directory endpointname:/taurusd/remote/dir -P`.
`rclone lsf endpointname:/taurusd/remote/dir` can list the directories (`ls` instead of `lsf` will list recursively).
You can also mount the directory as `rclone mount endpointname:/taurusd/ /mount/point --no-modtime`. But if your path contains large directories the access would be slow.
