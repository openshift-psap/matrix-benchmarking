#! /bin/bash

set -e
set -o pipefail
set -o nounset

SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

BENCHMARK_NAME=runai_gpu-burn
NAMESPACE=runai-hello
RUNAIJOB_TEMPLATE=$SCRIPT_DIR/gpu-burn/runaijob_gpu-burn_template.yaml
CM_ENTRYPOINT=$SCRIPT_DIR/gpu-burn/000_configmap_gpu-burn_entrypoint.yml
CM_GPU_BURN_SRC=$SCRIPT_DIR/gpu-burn/000_configmap_gpu-burn_src.yml

if tty -s; then
    ARTIFACT_BASE="/tmp/matrix-benchmarking_$(date +%Y%m%d)"
    mkdir -p "$ARTIFACT_BASE"

    ARTIFACT_DIR="$ARTIFACT_BASE/$(printf '%03d' $(ls "${ARTIFACT_BASE}/" | grep __ | wc -l))__benchmark__$BENCHMARK_NAME"

    mkdir -p "$ARTIFACT_DIR"

    echo "Running interactively."
    echo "Using '$ARTIFACT_DIR' to store the test artifacts."
else
    echo "Running non-interactively."
    ARTIFACT_DIR="$(pwd)"
    echo "Using the current directory to store the test artifacts ($ARTIFACT_DIR)."
fi

for i in "$@"; do
    key=$(echo $i | cut -d= -f1)
    val=$(echo $i | cut -d= -f2)
    declare $key=$val # defines a variable 'key'
    echo "$key ==> $val"
done

echo
echo "Running Run.AI GPU-Burn benchmark for $execution_time seconds at '$fraction'."
echo

cp "$CM_ENTRYPOINT" "$CM_GPU_BURN_SRC" "$ARTIFACT_DIR"
oc apply -n "$NAMESPACE" -f "$CM_ENTRYPOINT"
oc apply -n "$NAMESPACE" -f "$CM_GPU_BURN_SRC"

cat "$RUNAIJOB_TEMPLATE" \
    | sed "s/{{ gpu_burn_fraction }}/$fraction/" \
    | sed "s/{{ gpu_burn_time }}/$execution_time/" \
          > "$ARTIFACT_DIR/001_runaijob_gpu-burn.yaml"

oc delete -n "$NAMESPACE" -f "$ARTIFACT_DIR/001_runaijob_gpu-burn.yaml"
oc create -n "$NAMESPACE" -f "$ARTIFACT_DIR/001_runaijob_gpu-burn.yaml"

echo "Waiting for the Run.ai Job to succeed ..."
oc -n "$NAMESPACE" get runaijobs/gpu-burn
oc -n "$NAMESPACE" get pods -lapp=gpu-burn

while [[ $(oc get runaijobs/gpu-burn -ojsonpath={.status.succeeded}) != 1 ]]; do
    sleep 10
    oc -n "$NAMESPACE" get pods -lapp=gpu-burn
done

oc get -n "$NAMESPACE" runaijobs/gpu-burn -oyaml > "$ARTIFACT_DIR/runaijob.status.yaml"

for pod_name in $(oc get -n "$NAMESPACE" pods -oyaml -lapp=gpu-burn -oname); do
    oc -n "$NAMESPACE" get $pod_name -oyaml > $ARTIFACT_DIR/runai_$(basename $pod_name).status.yaml
    oc -n "$NAMESPACE" logs $pod_name > $ARTIFACT_DIR/runai_$(basename $pod_name).log
done

echo "Done, artifacts saved in $ARTIFACT_DIR"
