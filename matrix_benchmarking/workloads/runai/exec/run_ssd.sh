#! /bin/bash

#! /bin/bash

set -e
set -o pipefail
set -o nounset

SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

for i in "$@"; do
    key=$(echo $i | cut -d= -f1)
    val=$(echo $i | cut -d= -f2)
    declare $key=$val
    echo "$key ==> $val"
done
echo

if tty -s; then
    ARTIFACT_BASE="/tmp/ci-artifacts_$(date +%Y%m%d)"
    mkdir -p "$ARTIFACT_BASE"

    ARTIFACT_DIR="$ARTIFACT_BASE/$(printf '%03d' $(ls "${ARTIFACT_BASE}/" | grep __ | wc -l))__ssd"

    mkdir -p "$ARTIFACT_DIR"

    echo "Running interactively."
    echo "Using '$ARTIFACT_DIR' to store the test artifacts."
else
    echo "Running non-interactively."
    ARTIFACT_DIR="$(pwd)"
    echo "Using the current directory to store the test artifacts ($ARTIFACT_DIR)."
fi

NAMESPACE=matrix-benchmarking
IMAGE=quay.io/openshift-psap/nvidiadl-ssd-training-benchmark:ssd # "aiml:ssd"
INFERENCE_SCRIPT_NAME="SSD320_FP${fp}_inference.sh "
NGPU=1
TRAINING_SCRIPT_NAME="SSD320_FP${fp}_${NGPU}GPU_BENCHMARK.sh"

# delete any stalled resource

echo "Deleting RunAIJobs ..."
oc delete runaijobs -lmatrix-benchmarking -n $NAMESPACE
echo "Deleting Pods ..."
oc delete pods -lmatrix-benchmarking --ignore-not-found -n $NAMESPACE

# instantiate the workload
all_training_pod_names=()
all_inference_pod_names=()
pod_index=0
create_pod() {
    idx=$1
    shift
    mode=$1
    shift
    fraction=$1

    NAME=ssd-$mode
    if [[ "$mode" == "inference" ]]; then
        script_name=$INFERENCE_SCRIPT_NAME
    else
        script_name=$TRAINING_SCRIPT_NAME
    fi

    if [[ "$partionner" == "runai" ]]; then
        template_filename=${SCRIPT_DIR}/runaijob_template.yaml
        type=runaijob
    else
        template_filename=${SCRIPT_DIR}/pod-run-aiml_template.yaml
        type=pod
    fi
    name="ssd-${mode}-${idx}"

    # instantiate the template
    pod_file="${ARTIFACT_DIR}/$(printf "%04d" $pod_index)_${type}_$name.yaml"
    cat "$template_filename" \
        | sed "s/{{ name }}/$name/g" \
        | sed "s/{{ namespace }}/$NAMESPACE/g" \
        | sed "s|{{ image }}|$IMAGE|g" \
        | sed "s|{{ mode }}|$mode|g" \
        | sed "s|{{ script_name }}|$script_name|g" \
        | sed "s|{{ inference_time }}|${inference_time:-}|g" \
        | sed "s|{{ fraction }}|$fraction|g" \
              > "$pod_file"

    pod_index=$(($pod_index + 1))

    # create the pod
    pod_name=$(oc create -f "$pod_file" -oname -n $NAMESPACE)

    if [[ "$partionner" == "runai" ]]; then
        echo "Waiting for Run.AI to create the pod for '$pod_name' ..."
        pod_name=""
        while [[ -z "$pod_name" ]]; do
            sleep 1
            pod_name=$(oc get pods -ljob-name=$name -oname -n $NAMESPACE)
        done
        echo "Done, found pod $pod_name"
    fi

    if [[ "$mode" == "inference" ]]; then
        all_inference_pod_names+=($pod_name)
    else
        all_training_pod_names+=($pod_name)
    fi
}

for mode in inference training; do
    count_var=${mode}_count
    fraction_var=${mode}_fraction
    for idx in $(seq ${!count_var}); do
        create_pod $idx $mode ${!fraction_var}
    done
done


do_wait_pods() {
    mode=$1
    if [[ "$mode" == "training" ]]; then
        all_pod_names=${all_training_pod_names[@]}
    else
        all_pod_names=${all_inference_pod_names[@]}
    fi
    echo "Waiting for the completion of the $mode pods ...  ${all_pod_names[@]}"
    for pod_name in ${all_pod_names[@]};
    do
        phase=Pending
        while [[ "$phase" == "Pending" || "$phase" == "Running"  ]]; do
            sleep 10
            new_phase=$(oc get $pod_name -ocustom-columns=phase:status.phase --no-headers -n $NAMESPACE)
            if [[ "$new_phase" != "$phase" ]]; then
                echo "$(date) $pod_name $new_phase"
                phase=$new_phase
            fi
        done
        echo "Pod $pod_name is done ($phase)."
    done
    echo "All the $mode pods have completed their execution."
}

do_collect() {
    echo "Collecting artifacts in $ARTIFACT_DIR ..."
    # collect artifacts
    oc get nodes -oyaml -n $NAMESPACE > "$ARTIFACT_DIR/nodes.yaml"

    for pod_name in ${all_training_pod_names[@]} ${all_inference_pod_names[@]};
    do
        name=$(basename "$pod_name")

        oc describe $pod_name -n $NAMESPACE > "$ARTIFACT_DIR/pod_${name}.descr"
        oc get -oyaml $pod_name -n $NAMESPACE > "$ARTIFACT_DIR/pod_${name}.status.yaml"
        oc logs $pod_name -n $NAMESPACE > "$ARTIFACT_DIR/pod_${name}.log"
    done

    if [[ "$partionner" == "runai" ]]; then
        for runaijob_name in $(oc get runaijobs -oname -n $NAMESPACE);
        do
            name=$(basename "$runaijob_name")
            oc describe $runaijob_name -n $NAMESPACE > "$ARTIFACT_DIR/runaijob_${name}.descr"
            oc get -oyaml $runaijob_name -n $NAMESPACE > "$ARTIFACT_DIR/runaijob_${name}.status.yaml"
        done
    fi
}

do_destroy_runai_jobs() {
    oc delete runaijobs -lmatrix-benchmarking -n $NAMESPACE
}

do_exit() {
    set -x
    has_not_succeeded=$(oc get pods -lmatrix-benchmarking -ocustom-columns=phase:status.phase --no-headers -n $NAMESPACE \
                            | egrep -v '(Terminating|Succeeded|Running)' || true)

    echo "Status: $has_not_succeeded"
    if [[ "$has_not_succeeded" ]]; then
        echo "Failed"
        exit 1
    fi

    echo "All good."
    exit 0
}

do_wait_pods "training"
if [[ "${inference_time:-}" || "${training_count:-0}" == 0 ]]; then
    do_wait_pods "inference"
fi
do_collect
do_destroy_runai_jobs
do_exit
