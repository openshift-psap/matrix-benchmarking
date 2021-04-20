#! /bin/bash

set -x

NODE_NAME=perf23-nva100
NVIDIA_DRIVER_ROOT=/run/nvidia/driver
NAMESPACE=gpu-operator-resources

MIG_CONFIG=$1

trap "trap - SIGTERM && kill -- ${$}" SIGINT SIGTERM EXIT

kubectl label --overwrite \
	node ${NODE_NAME} \
	nvidia.com/gpu.deploy.device-plugin=false \
	nvidia.com/gpu.deploy.gpu-feature-discovery=false \
	nvidia.com/gpu.deploy.dcgm-exporter=false

kubectl wait --for=delete pod \
	--timeout=5m \
	-n gpu-operator-resources \
	-l app=nvidia-device-plugin-daemonset

kubectl wait --for=delete pod \
	--timeout=5m \
	-n gpu-operator-resources \
	-l app=gpu-feature-discovery

kubectl wait --for=delete pod \
	--timeout=5m \
	-n gpu-operator-resources \
	-l app=nvidia-dcgm-exporter

kubectl delete pod nvidia-mig-parted-${NODE_NAME}

cat <<EOF | kubectl apply -f - || exit 1
apiVersion: v1
kind: Pod
metadata:
  name: nvidia-mig-parted-${NODE_NAME}
  labels:
    app: nvidia-mig-parted-${NODE_NAME}
  namespace: ${NAMESPACE}
spec:
  restartPolicy: Never
  hostPID: true
  hostIPC: true
  containers:
  - name: nvidia-mig-parted
    image: quay.io/kpouget/mig-parted:operator
    imagePullPolicy: IfNotPresent
    command: ["nvidia-mig-parted", "apply"]
    env:
    - name: MIG_PARTED_DEBUG
      value: 'true'
    - name: MIG_PARTED_CONFIG_FILE
      value: "/mig-parted-config/nva100_mig-parted_config.yaml"
    - name: MIG_PARTED_SELECTED_CONFIG
      value: "${MIG_CONFIG}"
    securityContext:
      privileged: true
    volumeMounts:
    - mountPath: /sys
      name: host-sys
    - mountPath: /mig-parted-config
      name: mig-parted-config
  volumes:
  - name: host-sys
    hostPath:
      path: /sys
      type: Directory
  - name: mig-parted-config
    configMap:
      name: nvidia-mig-mode
EOF

while [ "$(kubectl logs pod/nvidia-mig-parted-${NODE_NAME})" = "" ];do sleep 1; done

kubectl logs pod/nvidia-mig-parted-${NODE_NAME} -f &

wait -n ${!}

if false; then
    kubectl wait --for=phase=Succeeded pod \
	--timeout=5m \
	-n ${NAMESPACE} \
	-l app=nvidia-mig-parted-${NODE_NAME} &

    complete_pid=${!}

    kubectl wait --for=condition=failed pod \
	--timeout=5m \
	-n ${NAMESPACE} \
	-l app=nvidia-mig-parted-${NODE_NAME} && exit 1 &

    failed_pid=${!}

    wait -n ${complete_pid} ${failed_pid}
    result=${?}

    [ "${result}" != "0" ] && exit 1
else

    while true; do
          phase=$(oc get -o custom-columns=:.status.phase pods -l app=nvidia-mig-parted-${NODE_NAME} --no-headers)
          if echo $phase | egrep 'Succeeded|Error|Failed'; then
             break
          else
              sleep 5;
          fi
    done
    if ! echo $phase | grep 'Succeeded'; then
        echo "failed"
        exit 1
    fi
fi

kubectl label --overwrite \
	node ${NODE_NAME} \
	nvidia.com/gpu.deploy.device-plugin=true \
	nvidia.com/gpu.deploy.gpu-feature-discovery=true \
	nvidia.com/gpu.deploy.dcgm-exporter=true

kubectl wait --for=condition=ready pod \
	--timeout=5m \
	-n gpu-operator-resources \
	-l app=nvidia-device-plugin-daemonset

kubectl wait --for=condition=ready pod \
	--timeout=5m \
	-n gpu-operator-resources \
	-l app=gpu-feature-discovery

kubectl wait --for=condition=ready pod \
	--timeout=5m \
	-n gpu-operator-resources \
	-l app=nvidia-dcgm-exporter

kubectl delete pod \
        --ignore-not-found=true \
	-n ${NAMESPACE} \
	nvidia-device-plugin-validation

trap - EXIT

exit 0
