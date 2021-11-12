#!/bin/bash

# base file at https://github.com/mlcommons/training_results_v0.7/blob/master/NVIDIA/benchmarks/ssd/implementations/pytorch/run_and_time.sh

# Copyright (c) 2018-2019, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# runs benchmark and reports time to convergence
# to use the script:
#   run_and_time.sh
export NCCL_DEBUG=INFO

set -e
set -x

nvidia-smi -L

NB_GPUS=$(nvidia-smi -L | grep "UUID: MIG-" | wc -l)
if [[ "$NB_GPUS" == 0 ]]; then
    ALL_GPUS=$(nvidia-smi -L | grep "UUID: GPU" | cut -d" " -f6 | cut -d')' -f1)
    NB_GPUS=$(nvidia-smi -L | grep "UUID: GPU" | wc -l)
    MIG_MODE=0

    if [[ "$GPU_RES_TYPE" != "nvidia.com/gpu" ]]; then
        echo "FATAL: Expected full GPUs, got MIG GPUs ..."
        exit 1
    fi

    echo "No MIG GPU available, using the full GPUs ($ALL_GPUS)."
else
    ALL_GPUS=$(nvidia-smi -L | grep "UUID: MIG-" | awk '{ printf $6"\n"}' | cut -d')' -f1)
    MIG_MODE=1

    if [[ "$GPU_RES_TYPE" == "nvidia.com/gpu" ]]; then
        echo "FATAL: Expected MIG GPUs, got full GPUs ..."
        exit 1
    fi

    echo "Found $NB_GPUS MIG instances: $ALL_GPUS"
fi

if [[ $NB_GPUS != $GPU_COUNT ]]; then
    echo "FATAL: Expected $GPU_COUNT GPUs, got $NB_GPUS"
    exit 1
fi

SSD_THRESHOLD=${SSD_THRESHOLD:-0.23}

# start timing
start=$(date +%s)
start_fmt=$(date +%Y-%m-%d\ %r)
echo "STARTING TIMING RUN AT $start_fmt $GPU_MODE"

# run benchmark
set -x
NUMEPOCHS=${NUMEPOCHS:-80}

echo "running benchmark"

export DATASET_DIR="/data/coco2017"
export TORCH_HOME="${DATASET_DIR}/torchvision"

# prepare dataset according to download_dataset.sh

if [ ! -f ${DATASET_DIR}/annotations/bbox_only_instances_val2017.json ]; then
    echo "Prepare instances_val2017.json ..."
    ./prepare-json.py --keep-keys \
        "${DATASET_DIR}/annotations/instances_val2017.json" \
        "${DATASET_DIR}/annotations/bbox_only_instances_val2017.json"
fi

if [ ! -f ${DATASET_DIR}/annotations/bbox_only_instances_train2017.json ]; then
    echo "Prepare instances_train2017.json ..."
    ./prepare-json.py \
        "${DATASET_DIR}/annotations/instances_train2017.json" \
        "${DATASET_DIR}/annotations/bbox_only_instances_train2017.json"
fi

# prepare the DGXA100-specific configuration (config_DGXA100.sh)

EXTRA_PARAMS='--batch-size=114 --warmup=650 --lr=3.2e-3 --wd=1.3e-4'

DGXNSOCKET=1
DGXSOCKETCORES=${DGXSOCKETCORES:-16}

if [[ $MIG_MODE == "1" ]]; then
   DGXNGPU=1
   echo "Running in parallel mode."

else
    DGXNGPU=$NB_GPUS
    echo "Running in multi-gpu mode."
fi

# run training

declare -a CMD
CMD=('python' '-u' '-m' 'bind_launch' "--nsockets_per_node=${DGXNSOCKET}" \
               "--ncores_per_socket=${DGXSOCKETCORES}" "--nproc_per_node=${DGXNGPU}" )

declare -a ARGS
ARGS=(train.py
  --use-fp16
  --nhwc
  --pad-input
  --jit
  --delay-allreduce
  --opt-loss
  --epochs "${NUMEPOCHS}"
  --warmup-factor 0
  #--evaluation 5 10 15 20 25 30 35 40 50 55 60 65 70 75 80 85
  --no-save
  --threshold=${SSD_THRESHOLD}
  --data ${DATASET_DIR}
  ${EXTRA_PARAMS})

if [[ "$EXECUTION_MODE" == "dry" ]]; then
    echo "Running in dry mode"
    CMD[0]="echo"
fi

declare -a pids

trap "date; echo failed; exit 1" ERR

if [[ "$OVER_REQUESTING" != "y" ]]; then
    SYNC_DIR=$DATASET_DIR/sync/

    mkdir -p "$SYNC_DIR"

    for sync_f in "$SYNC_DIR/"*; do
        if [[ "$sync_f" != "$DATASET_DIR/$SYNC_IDENTIFIER" ]]; then
            rm -f "$sync_f"
        fi
    done

    set +x
    echo "$(date) Waiting for all the $SYNC_COUNTER Pods to start ..."
    touch "$DATASET_DIR/sync/$SYNC_IDENTIFIER"
    if grep $(hostname) "$DATASET_DIR/sync/$SYNC_IDENTIFIER"; then
        echo "ERROR: $(hostname) already in the sync file ..."
        cat "$DATASET_DIR/sync/$SYNC_IDENTIFIER"
        exit 1
    fi


    echo $(hostname) >> "$DATASET_DIR/sync/$SYNC_IDENTIFIER"
    while true; do
        cnt=$(cat "$DATASET_DIR/sync/$SYNC_IDENTIFIER" | wc -l)
        [[ $cnt == "$SYNC_COUNTER" ]] && break
        echo "Found $cnt Pods, waiting to have $SYNC_COUNTER ..."
        sleep 5
    done
    echo "$(date) All the $SYNC_COUNTER Pods are running, launch the GPU workload."
    cat "$DATASET_DIR/sync/$SYNC_IDENTIFIER"
    set -x
else
    echo "Over requesting mode enabled, do not wait for $SYNC_COUNTER Pods ..."
fi

nvidia-smi -L

if [[ $MIG_MODE == 1 ]]; then
    for gpu in $(echo "$ALL_GPUS"); do
        export NVIDIA_VISIBLE_DEVICES=$gpu
        export CUDA_VISIBLE_DEVICES=$gpu

        dest=/tmp/ssd_$(echo $gpu | sed 's|/|_|g').log

        # run training
        "${CMD[@]}" "${ARGS[@]}" > "$dest" &
        pids+=($!)
        echo "Running on $gpu ===> $dest: PID $!"
    done
    echo "$(date): waiting for parallel $NB_GPUS executions: ${pids[@]}"
else
    dest=/tmp/ssd_all.log

    "${CMD[@]}" "${ARGS[@]}" > "$dest" &
    pids+=($!)
    echo "Running on all the GPUs ===> $dest: PID $!"

    echo "$(date): waiting for 1 execution: ${pids[@]}"

fi

if [[ "$EXECUTION_MODE" == "dry" ]]; then
    sleep 1s #2m
fi

for pid in ${pids[@]};
do
    wait $pid
done

echo "$(date): done waiting for $NB_GPUS executions"

ls /tmp/ssd*
grep . /tmp/ssd_*.log

# end timing
end=$(date +%s)
end_fmt=$(date +%Y-%m-%d\ %r)
echo "START TIMING RUN WAS $start_fmt"
echo "ENDING TIMING RUN AT $end_fmt"

nvidia-smi -L

# report result
result=$(($end - $start))
result_name="SINGLE_STAGE_DETECTOR"

echo "RESULT,$result_name,,$result,nvidia,$start_fmt"
echo "ALL FINISHED $GPU_MODE"
