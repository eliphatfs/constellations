from kubernetes import client, config
import collections

config.load_kube_config()
cfg = client.Configuration.get_default_copy()
cfg.assert_hostname = 'cazuhobftyq.cp.exqfzq.oraclevcn.com'
v1 = client.CoreV1Api(client.ApiClient(cfg))
pod_req = v1.list_namespaced_pod('default', async_req=True)
node_req = v1.list_node(async_req=True)

pods: client.V1PodList = pod_req.get()
nodes: client.V1NodeList = node_req.get()

usingPods = collections.defaultdict(list)

for pod in pods.items:
    pod: client.V1Pod
    try:
        if pod.status.phase == "Running":
            usingPods[pod.spec.node_name].append(pod)
    except AttributeError:
        pass

for node in nodes.items:
    node: client.V1Node
    try:
        node_avail = node_total = int(node.metadata.labels.get('nvidia.com/gpu.count'))
        here = []
        for pod in usingPods[node.metadata.name]:
            try:
                gpus = sum(int(c.resources.limits.get('nvidia.com/gpu') or 0) for c in pod.spec.containers)
                node_avail -= gpus
                here.append(pod.metadata.name + '(%d)' % gpus)
            except (AttributeError, KeyError, TypeError):
                pass
        print(node.metadata.name, "\t%d/%d available\t" % (node_avail, node_total), *here)
    except (AttributeError, KeyError, TypeError):
        pass
