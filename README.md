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

S3 endpoint URL: https://taurus-s3.skis.ltd:9033

`rclone` is recommended to deal with S3. `rclone --ca-cert weka.crt copy /local/file/or/directory endpointname:/taurusd/remote/dir -P`.
`rclone --ca-cert weka.crt lsf endpointname:/taurusd/remote/dir` can list the directories (`ls` instead of `lsf` will list recursively).
You can also mount the directory as `rclone --ca-cert weka.crt mount endpointname:/taurusd/ /mount/point --no-modtime`. But if your path contains large directories the access would be slow.
You can also mount a small sub-directory if you like. You can set Other as the provider when using rclone config.

There is a limit on chunk sizes and number of chunks per file currently. There cannot be more than 10000 chunks, and the chunk size is required to be within 5MiB to 5GiB. `rclone` defaults to 5MiB.
If you are uploading a single file larger than 50GB, add `--s3-chunk-size 100M`.
If you are uploading a single file larger than 1TiB, think again and don't do that.

`weka.crt` can be downloaded from this repository. For `aws`, it needs to be specified as `--ca-bundle weka.crt`.

Do not create other buckets. The files will not be available on the FS and may be deleted at any time.

## Caveat

Current persistent storage cannot be mounted on CPU nodes. If you are debugging, make sure you are selecting the GPU nodes via the nodeSelector `node.kubernetes.io/instance-type: BM.GPU.H100.8`.
