# Taurus Cluster

Taurus is composed of 8 compute nodes each with 8xH100 GPU cards and 3 control plane nodes without GPU.

## Access

Taurus is operated via Kubernetes. Read the quick start of Nautilus (https://docs.nationalresearchplatform.org/userdocs/start/quickstart/) if you know nothing about Kubernetes.

You will get a config from the administrator. Put it into `~/.kube/config` or use

```bash
export KUBECONFIG=<path/to/config>
```

to set the current kubectl config for the terminal session.

## Workloads

Submitting workloads are similar to Nautilus as we are both using Kubernetes.
You can use pods, jobs and deployments.

### Limit Range Policy

To avoid oversubscription, we currently require memory limit to be the same as requests, and CPU limit be within 1.0x to 1.5x of requests.

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

### RoCE and Cross-node Workload

**Note: k8s is a sequential scheduler which means it can spin up your workload nodes separately if there is no sufficient resources.**

For a cross-node workload, there are two parts: a way to discover the other nodes inside the workload; and how to configure each workload.

Discovery is implemented using k8s headless services. It essentially finds the master node (with rank 0) and sets up DNS to it.

Remember to delete the service after you finish with your job. You can use `kubectl delete -f <yaml>` for that.

The container image is required to have IB support to use RoCE. If not, you can install with

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get -q install -y -f build-essential pkg-config vlan automake autoconf dkms git libibverbs* librdma* libibmad.* libibumad* libtool ibutils ibverbs-utils rdmacm-utils infiniband-diags perftest librdmacm-dev libibverbs-dev numactl libnuma-dev libnl-3-200 libnl-route-3-200 libnl-route-3-dev libnl-utils ibutils
```

Replace `<your-exp-name>` and `<your-account-name>` in the config.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: <your-exp-name>-discovery
spec:
  clusterIP: None
  selector:
    job-name: <your-exp-name>-job
    completion-index: "0"
  ports:
    - protocol: TCP
      port: 6006
      targetPort: 6006
---
apiVersion: batch/v1
kind: Job
metadata:
  name: <your-exp-name>-job
spec:
  completions: 2  # node count here
  parallelism: 2  # node count here
  completionMode: Indexed
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      # this is necessary for RoCE to attach!
      annotations:
        k8s.v1.cni.cncf.io/networks: oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov,oci-rdma-sriov
    spec:
      # if you forget your account name, ask the cluster admin
      serviceAccount: <your-account-name>
      # an init container is used to tag the pod with its rank for service discovery
      initContainers:
        - command:
            - /bin/bash
            - -c
            - |
              kubectl label pod ${POD_NAME} completion-index=${JOB_COMPLETION_INDEX}
          image: aga.ocir.io/hpc_limited_availability/oke/kubectl:latest
          name: discovery-setup
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
      # the main workload comes here
      containers:
        - name: gpu-container
          image: eliphatfs/zero123plus:0.20.2-ib
          command: ["/bin/bash"]
          # a minimal example. change to your actual workload.
          args:
            - "-c"
            - |
              cd;
              env | grep JOB_COMPLETION_INDEX;
              env | grep MASTER_ADDR;
              ulimit -a;
              apt -qq update && apt -q install -y git >/dev/null;
              git clone https://github.com/eliphatfs/minimal-ddp-example.git &&
              cd minimal-ddp-example &&
              NCCL_DEBUG="INFO" python -m torch.distributed.launch \
                --nnodes 2 \
                --nproc-per-node 8 \
                --master-port ${MASTER_PORT} \
                --master-addr ${MASTER_ADDR} \
                --node-rank ${JOB_COMPLETION_INDEX} \
                minimal_ddp.py
          # flags starting from `NCCL_NET` are recommended configurations from Oracle team
          # you can play around them if you want, but the settings here should be okay for the most times
          env:
            - name: MASTER_ADDR
              value: <your-exp-name>-discovery
            - name: MASTER_PORT
              value: "6006"
            - name: NCCL_NET
              value: "IB"
            - name: NCCL_CROSS_NIC
              value: "0"
            - name: NCCL_SOCKET_NTHREADS
              value: "16"
            - name: NCCL_CUMEM_ENABLE
              value: "0"
            - name: NCCL_IB_SPLIT_DATA_ON_QPS
              value: "0"
            - name: NCCL_IB_QPS_PER_CONNECTION
              value: "16"
            - name: NCCL_IB_GID_INDEX
              value: "3"
            - name: NCCL_IB_TC
              value: "41"
            - name: NCCL_IB_SL
              value: "0"
            - name: NCCL_IB_TIMEOUT
              value: "22"
            - name: NCCL_NET_PLUGIN
              value: "0"
            - name: HCOLL_ENABLE_MCAST_ALL
              value: "0"
            - name: coll_hcoll_enable
              value: "0"
            - name: UCX_TLS
              value: "tcp"
            - name: UCX_NET_DEVICES
              value: "eth0"
            - name: RX_QUEUE_LEN
              value: "8192"
            - name: IB_RX_QUEUE_LEN
              value: "8192"
            - name: NCCL_SOCKET_IFNAME
              value: "eth0"
            - name: NCCL_IGNORE_CPU_AFFINITY
              value: "1"
            - name: NCCL_TOPO_FILE
              value: "/topo/topo.xml"
          # partial requests for GPU and SRIOV devices are not supported for cross-node RoCE workloads. Specify 8 and 16, respectively.
          resources:
            requests:
              cpu: "64"
              memory: "128Gi"
              nvidia.com/gpu: "8"
              nvidia.com/sriov_rdma_vf: "16"
              ephemeral-storage: 300Gi
            limits:
              cpu: "64"
              memory: "128Gi"
              nvidia.com/gpu: "8"
              nvidia.com/sriov_rdma_vf: "16"
              ephemeral-storage: 300Gi
          volumeMounts:
            - name: dshm
              mountPath: /dev/shm
            - name: taurusd-pvc
              mountPath: /taurusd
            - name: topo
              mountPath: /topo
      volumes:
        - name: taurusd-pvc
          persistentVolumeClaim:
            claimName: taurusd-pvc
        - name: dshm
          emptyDir:
            medium: Memory
        - name: topo
          configMap:
            name: nccl-topology
            items:
            - key: topo.xml
              path: topo.xml
      restartPolicy: Never
  backoffLimit: 0  # The number of attempts to restart after crash
```

## Persistent Storage

The current storage is backed by WEKA, and can support high-performance small-file IO.
See the example GPU pod for mounting the storage.

The storage is exposed to the web via a S3 interface.
The bucket `taurusd` is synchronized with the `/taurusd` mount shown in the GPU pod.

### Rclone Quick Start

`rclone` is recommended to deal with S3. You can install with `apt install rclone` or download from their website https://rclone.org/downloads/.

Run `rclone config` and add a new backend.

Storage: Amazon S3 Compliant Storage Providers (enter `s3`) <br/>
S3 provider: Other <br/>
Access key: You will get your access key and secret from the cluster admin. <br/>
Endpoint: https://taurus-s3.skis.ltd:9033

**Copy:** `rclone --ca-cert weka.crt copy /local/file/or/directory endpointname:/taurusd/remote/dir -P`.

**List:** `rclone --ca-cert weka.crt lsf endpointname:/taurusd/remote/dir` can list the directories (`ls` instead of `lsf` will list recursively).

**Mount:**
You can also mount the directory as `rclone --ca-cert weka.crt mount endpointname:/taurusd/ /mount/point --no-modtime`. But if your path contains large directories the access would be slow.
You can also mount a small sub-directory if you like. You can set Other as the provider when using rclone config.

**Performance and Limitations:**
There is a limit on chunk sizes and number of chunks per file currently. There cannot be more than 10000 chunks, and the chunk size is required to be within 5MiB to 5GiB. `rclone` defaults to 5MiB.
If you are uploading a single file larger than 50GB, add `--s3-chunk-size 100M`.
If you are uploading a single file larger than 1TiB, think again and don't do that.
It is recommended to keep the file chunks fewer than 1000 for the best performance, i.e. it is recommended to increase the chunk size if your file is about or larger than 5GB.

**Sync:**
rclone can also run as a remote rsync. `rclone  --ca-cert weka.crt sync local-directory-or-file endpointname:/taurusd/your/target/directory -P`.

**weka.crt**
`weka.crt` can be downloaded from this repository. For `aws`, it needs to be specified as `--ca-bundle weka.crt`.

**Do not create other buckets. The files will not be available on the FS and may be deleted at any time.**

### Caveat

Current persistent storage cannot be mounted on CPU nodes. If you are not requesting GPU in workloads such as SSH and data transfer, make sure you are selecting the GPU nodes via the nodeSelector `node.kubernetes.io/instance-type: BM.GPU.H100.8`.

Add this to the pod spec (same level with `volumes`):
```
tolerations:
  - effect: NoSchedule
    key: nvidia.com/gpu
    operator: Exists
nodeSelector:
  node.kubernetes.io/instance-type: BM.GPU.H100.8
```
