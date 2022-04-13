import kubernetes.client
import kubernetes.config
import kubernetes.utils
from kubernetes.stream import stream as k8s_stream

from kubernetes.client import V1ConfigMap, V1ObjectMeta

kubernetes.config.load_kube_config()

corev1 = kubernetes.client.CoreV1Api()
appsv1 = kubernetes.client.AppsV1Api()
batchv1 = kubernetes.client.BatchV1Api()
custom = kubernetes.client.CustomObjectsApi()

k8s_client = kubernetes.client.ApiClient()
