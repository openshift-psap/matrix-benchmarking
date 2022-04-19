#! /bin/bash

set -e
set -o pipefail
set -o nounset

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if tty -s; then
    ARTIFACT_BASE="/tmp/ci-artifacts_$(date +%Y%m%d)"
    mkdir -p "$ARTIFACT_BASE"

    ARTIFACT_DIR="$ARTIFACT_BASE/$(printf '%03d' $(ls "${ARTIFACT_BASE}/" | grep __ | wc -l))__benchmark__mpi-benchmark"

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
    declare $key=$val
    echo "$key ==> $val"
done
echo

common_args=""
common_args="$common_args -name $operation -machine $machine"
extra_args=""

if [[ "${node_count:-}" ]]; then
    extra_args="$extra_args -np $node_count"
    worker_node_count=$(oc get nodes -oname -l node-role.kubernetes.io/worker | wc -l)
    if [[ $node_count -gt $worker_node_count ]];
    then
        echo "ERROR: requested $node_count nodes, but the cluster only has $worker_node_count worker nodes ..."
        exit 1
    fi
fi

# delete any stalled resource
mpijobs="$(oc get mpijobs -oname)"
if [[ "$mpijobs" ]]; then
    oc delete $mpijobs
fi

# mpijobs jobs do not have labels ...
for mpijob_name in $(oc get mpijobs '-ojsonpath={range .items[*]}{.metadata.name}{"\n"}{end}');
do
    oc delete job/${mpijob_name}-launcher --ignore-not-found
done
oc delete pods -ltraining.kubeflow.org/operator-name=mpi-operator

echo "Waiting for all the MPI Operator pods to disappear ..."
while [[ "$(oc get pods -ltraining.kubeflow.org/operator-name=mpi-operator -oname)" ]]; do
    sleep 5
done
echo "Done."

cmd="go run apply_template.go $common_args $extra_args"
echo $cmd
mpi_yaml=$(cd "$SCRIPT_DIR"; $cmd)

echo "$mpi_yaml" > "$ARTIFACT_DIR/001_mpijob.yaml"

mpijob_name=$(echo "$mpi_yaml" | oc create -f- -oname --dry-run=client) # eg: mpijob.kubeflow.org/osu-alltoall-4procs
name=$(echo "$mpi_yaml" | oc create -f- -ojsonpath={.metadata.name}) # eg: osu-alltoall-4procs

echo
echo "Waiting for $mpijob_name to complete its execution ..."
while [[ -z "$(oc get "$mpijob_name" -ojsonpath={.status.completionTime})" ]];
do
    echo -n "."
    sleep 5
done
echo
echo "Done, collecting artifacts in $ARTIFACT_DIR ..."

oc get "$mpijob_name" -oyaml > "$ARTIFACT_DIR/mpijob.status.yaml"

oc get pods -ltraining.kubeflow.org/job-name=$name -oyaml > "$ARTIFACT_DIR/mpijob.pods.yaml"

for pod in $(oc get pods -ltraining.kubeflow.org/job-name=$name,training.kubeflow.org/job-role=worker -oname); do
    oc logs $pod > "$ARTIFACT_DIR/mpijob.$(echo "$pod" | sed "s|pod/${name}-||").log"
done

oc get nodes -oyaml >  "$ARTIFACT_DIR/nodes.yaml"

# if Pod logs are queried with the label selector, only the last lines are
launcher_pod_name=$(oc get pod -ltraining.kubeflow.org/job-name=$name,training.kubeflow.org/job-role=launcher -oname)

if [[ -z "$launcher_pod_name" ]]; then
    echo "ERROR: the launcher Pod disappeared ..."
    exit 1
fi

oc logs "$launcher_pod_name" > "$ARTIFACT_DIR/mpijob.launcher.log"

echo

cat "$ARTIFACT_DIR/mpijob.launcher.log"

echo "All done."
