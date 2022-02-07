# Prepare the cluster operators

1. Install NFD Operator
   - don't forget to create the NodeFeatureDiscoveries

2. Install the NVIDIA GPU Operator
   - don't forgot to create the ClusterPolicy

2. Install the Local Storage Operator
   - see next step for the creation of a LocalVolume

# Setup the storage

1. Create the local disk storage class

```
DISK_DEV=/dev/nvme2n1
STORAGE_CLASS_NAME=local-sc-dgx
NODE_NAME=dgxa100

cat <<EOF | oc apply -f-
apiVersion: local.storage.openshift.io/v1
kind: LocalVolume
metadata:
  name: local-disks
  namespace: openshift-local-storage
spec:
  nodeSelector:
    nodeSelectorTerms:
    - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - $NODE_NAME
  storageClassDevices:
    - storageClassName: $STORAGE_CLASS_NAME
      volumeMode: Filesystem
      fsType: xfs
      devicePaths:
        - $DISK_DEV
EOF
```

# Enable user-workload monitoring

```
cat <<EOF | oc apply -f-
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
EOF
```

# Prepare the dataset and image for the benchmark

1. Create the dataset PVC

```
PVC_NAME=benchmarking-coco-dataset
NAMESPACE=default
STORAGE_CLASS_NAME=local-sc-dgx

cat <<EOF | oc apply -f-
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $PVC_NAME
  namespace: $NAMESPACE
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 80Gi
  storageClassName: $STORAGE_CLASS_NAME
EOF
```

2. Populate the PVC with the coco-dataset

```
NODE_NAME=dgxa100
NAMESPACE=default
PVC_NAME=benchmarking-coco-dataset
./run_toolbox.py benchmarking download_coco_dataset $NODE_NAME \
                 --namespace $NAMESPACE \
                 --pvc-name $PVC_NAME
```

3. Build the MLPerf NVIDIA PyToch SSD image

```
oc patch configs.imageregistry.operator.openshift.io cluster --type merge --patch '{"spec":{"managementState":"Managed"}}'
oc patch configs.imageregistry.operator.openshift.io cluster --type merge --patch '{"spec":{"storage":{"emptyDir":{}}}}'
```

```
NAMESPACE=default
cat <<EOF | oc apply -f-
kind: ImageStream
apiVersion: image.openshift.io/v1
metadata:
  name: mlperf
  namespace: $NAMESPACE
  labels:
    app: mlperf
spec: {}
EOF
```

```
NAMESPACE=default
cat <<EOF | oc apply -f-
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  labels:
    app: mlperf
  name: mlperf0.7
  namespace: $NAMESPACE
spec:
  output:
    to:
      kind: ImageStreamTag
      name: mlperf:ssd_0.7
      namespace: default
  resources: {}
  source:
    type: Git
    git:
      uri: "https://github.com/kpouget/training_results_v0.7.git"
      ref: "master"
    contextDir: NVIDIA/benchmarks/ssd/implementations/pytorch
  triggers:
  - type: "ConfigChange"
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: Dockerfile
      from:
        kind: DockerImage
        name: nvcr.io/nvidia/pytorch:20.06-py3
EOF
```

# Allow extra MIG modes

```
oc apply -f mig-custom.yaml

set "/spec/migManager/config/name" = custom-mig-config
```

# Enable MIG metrics

```
oc patch clusterpolicy/gpu-cluster-policy --type='json' -p='[{"op": "replace", "path": "/spec/dcgmExporter/repository", "value": "nvcr.io/nvidia/k8s"}]'
oc patch clusterpolicy/gpu-cluster-policy --type='json' -p='[{"op": "replace", "path": "/spec/dcgmExporter/image", "value": "dcgm-exporter"}]'
oc patch clusterpolicy/gpu-cluster-policy --type='json' -p='[{"op": "replace", "path": "/spec/dcgmExporter/version", "value": "2.3.1-2.6.1-ubi8"}]'
```
