#! /bin/bash

if [[ -z "${NODE_NAME:-}" ]]; then
    echo "ERROR: NODE_NAME must be provided as an environment variable."
    exit 1
fi

oc() {
    echo oc $*
    echo
}

# ----

# App name

APP_NAME_FILE="src/app_name"
if ! [[ -e "$APP_NAME_FILE" ]]; then
    echo "FATAL: the app name file doesn't exist ..."
    exit 1
fi

APP_NAME=$(cat "$APP_NAME_FILE")

# App namespace

NAMESPACE_FILE="src/namespace"
if ! [[ -e "$NAMESPACE_FILE" ]]; then
    echo "FATAL: the namespace name file doesn't exist ..."
    exit 1
fi

NAMESPACE=$(cat "$NAMESPACE_FILE")
echo "# Using 'app-name=$APP_NAME' in namespace '$NAMESPACE'"
echo

# Cleanup

echo "# Deleting any existing Job ..."
oc delete -n $NAMESPACE -lapp=$APP_NAME

# MIG Strategy

MIG_STRATEGY_FILE="src/mig-strategy.txt"
if ! [[ -e "$MIG_STRATEGY_FILE" ]]; then
    echo "FATAL: the MIG strategy file doesn't exist ..."
    exit 1
fi

STRATEGY=$(cat "$MIG_STRATEGY_FILE" | cut -d= -f2)
echo "# Applying the MIG advertisement strategy '$STRATEGY' ..."
oc patch clusterpolicy/gpu-cluster-policy --type='json' -p='[{"op": "replace", "path": "/spec/mig/strategy", "value": "'$STRATEGY'"}]'

# MIG Label

MIG_LABEL_FILE="src/mig-label.txt"
if ! [[ -e "$MIG_LABEL_FILE" ]]; then
    echo "FATAL: the MIG label file doesn't exist ..."
    exit 1
fi

MIG_LABEL=$(cat "$MIG_LABEL_FILE" | cut -d= -f2)
echo "# Applying the MIG partitionning '$MIG_LABEL' ..."
oc label node/$NODE_NAME --overwrite "nvidia.com/mig.config=$MIG_LABEL"

# Entrypoint

ENTRYPOINT_CM_FILE="src/entrypoint.cm.yaml"
echo "# Creating the benchmark entrypoint ..."
if ! [[ -e $ENTRYPOINT_CM_FILE ]]; then
    echo "FATAL: The entrypoint ConfigMap file is missing ..."
    exit 1
fi

oc apply -f "$ENTRYPOINT_CM_FILE"

# Job files

JOB_FILES="src/job_spec.*.yaml"
if [[ $(echo $JOB_FILES) == "$JOB_FILES" ]]; then
    echo "FATAL: the job_spec YAML files do not exist ..."
    exit 1
fi

echo "# Creating the benchmark job from '$(echo $JOB_FILES)' ..."
for fname in $JOB_FILES; do
    oc create -f $fname
done
