#! /bin/bash

set -e
set -o pipefail
set -o nounset

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BENCHMARK_NAME=sample
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
echo "Running in mode '$mode/operation': $*"
echo

sleep 1

# Generate random metrics
if [[ "$mode" == "date" ]]; then
    echo "Saving the date ..."
    date +%s > "$ARTIFACT_DIR"/date
elif [[ "$mode" == "procs" ]]; then
    echo "Saving the number of processes ..."
    ps aux | wc -l > "$ARTIFACT_DIR"/procs
elif [[ "$mode" == "memfree" ]]; then
    echo "Saving the free memory ..."
    cat /proc/meminfo | grep MemFree | awk '{ print $2}' > "$ARTIFACT_DIR"/memfree
else
    echo "Invalid mode: $mode"
    exit 1
fi

echo "Done"

exit 0
