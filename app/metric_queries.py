"""Select the container ID currently reported by Kubernetes at each query time.

Old cAdvisor series can remain visible briefly after a container restart. A
Pod-level sum without this join can count both the old and current container.
"""
INFO='label_replace(kube_pod_container_info{namespace="sock-shop"}, "cid", "$1", "container_id", "containerd://(.*)")'
SELECTOR='{namespace="sock-shop",job="kubernetes-nodes-cadvisor",container!="",container!="POD"}'


def live(expression):
    return f'label_replace({expression}, "cid", "$1", "id", ".*/([a-f0-9]{{64}})") and on(namespace,pod,container,cid) {INFO}'


CPU=live(f'rate(container_cpu_usage_seconds_total{SELECTOR}[1m])')
MEMORY=live(f'container_memory_working_set_bytes{SELECTOR}')
REQUESTS='sum by (service,route) (rate(request_duration_seconds_count{namespace="sock-shop",job="kubernetes-service-endpoints"}[1m]))'
ERRORS='sum by (service,route) (rate(request_duration_seconds_count{namespace="sock-shop",job="kubernetes-service-endpoints",status_code=~"5.."}[1m]))'
QUERIES={
    'cpu':f'sum by (pod) ({CPU})',
    'memory':f'sum by (pod) ({MEMORY})',
    'ready':'kube_pod_status_ready{namespace="sock-shop",condition="true"}',
    'restarts':'kube_pod_container_status_restarts_total{namespace="sock-shop"}',
    'cpu_limit':'sum by (pod) (kube_pod_container_resource_limits{namespace="sock-shop",resource="cpu"})',
    'memory_limit':'sum by (pod) (kube_pod_container_resource_limits{namespace="sock-shop",resource="memory"})',
    'created':'kube_pod_created{namespace="sock-shop"}',
    'latency_mean':'sum by (service,route) (rate(request_duration_seconds_sum{namespace="sock-shop",job="kubernetes-service-endpoints"}[1m])) / '+REQUESTS,
    'error_rate':f'({ERRORS} / {REQUESTS}) or on(service,route) (0 * {REQUESTS})',
    'request_rate':REQUESTS,
}
