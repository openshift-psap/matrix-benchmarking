#! /bin/bash

set -eo pipefail;
set -x

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

cd "$THIS_DIR"

oc apply -f "gpu-burn/gpu_burn_cm_entrypoint.yml"

GPU_NODE_HOSTNAME="perf23-nva100"
GPU_BURN_DURATION="$1"
GPU_RESOURCES="$2"
NVIDIA_VISIBLE_DEVICES="$3"

oc --ignore-not-found=true delete pod/gpu-burn-$GPU_NODE_HOSTNAME -n default

echo "GPU_BURN_DURATION=$GPU_BURN_DURATION"
echo "GPU_RESOURCES=$GPU_RESOURCES"
echo "NVIDIA_VISIBLE_DEVICES=$NVIDIA_VISIBLE_DEVICES"

cat <<EOF | oc apply -f-
apiVersion: v1
kind: Pod
metadata:
  labels:
    app: gpu-burn
  name: gpu-burn-$GPU_NODE_HOSTNAME
  namespace: default
spec:
  restartPolicy: Never
  containers:
  - image: nvcr.io/nvidia/cuda:11.2.2-devel-ubi8
    imagePullPolicy: Always
    name: gpu-burn-ctr
    command:
    - /bin/entrypoint.sh
    volumeMounts:
    - name: entrypoint
      mountPath: /bin/entrypoint.sh
      readOnly: true
      subPath: entrypoint.sh
    env:
    - name: GPU_BURN_TIME
      value: "$GPU_BURN_DURATION"
    - name: NVIDIA_VISIBLE_DEVICES
      value: "$NVIDIA_VISIBLE_DEVICES"
    resources:
$GPU_RESOURCES
  volumes:
    - name: entrypoint
      configMap:
        defaultMode: 0700
        name: gpu-burn-entrypoint
  nodeSelector:
    nvidia.com/gpu.present: "true"
    kubernetes.io/hostname: "$GPU_NODE_HOSTNAME"

EOF

sleep $GPU_BURN_DURATION

while true; do
    pod_state=$(oc get pod/gpu-burn-$GPU_NODE_HOSTNAME \
       -n default \
       -o custom-columns=:.status.phase \
       --no-headers || true)
    if [[ "$pod_state" == Succeeded || "$pod_state" == Failed || "$pod_state" == Error ]]; then
        break
    fi
    sleep 10
done

oc logs pod/gpu-burn-$GPU_NODE_HOSTNAME -n default > /tmp/gpu_burn.log
echo "Log saved into /tmp/gpu_burn.log"

if grep FAULTY /tmp/gpu_burn.log; then
    echo "GPU Burn found a faulty computations"
    exit 102
fi

if [[ "$pod_state" != Succeeded ]]; then
    echo "GPU Burn pod failed ($pod_state)"
    exit 101
fi

echo "All done"
exit 0
