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

echo "Running with Parallel mode activated."

DGXNGPU=1

NB_GPU=$(nvidia-smi -L | grep "UUID: MIG-GPU" | wc -l)
if [[ "$NB_MIG_GPU" == 0 ]]; then
    ALL_GPUS=$(nvidia-smi -L | grep "UUID: GPU" | cut -d" " -f5 | cut -d')' -f1)

    echo "No MIG GPU available, using the full GPUs ($ALL_GPUS)."
else
    ALL_GPUS=$(nvidia-smi -L | grep "UUID: MIG-GPU" | cut -d" " -f8 | cut -d')' -f1)
    echo "Found $NB_MIG_GPU MIG instances: $ALL_GPUS"
fi

DGXNSOCKET=1
DGXSOCKETCORES=${DGXSOCKETCORES:-16}
SSD_THRESHOLD=${SSD_THRESHOLD:-0.23}

# start timing
start=$(date +%s)
start_fmt=$(date +%Y-%m-%d\ %r)
echo "STARTING TIMING RUN AT $start_fmt"

# run benchmark
set -x
NUMEPOCHS=${NUMEPOCHS:-80}

echo "running benchmark"
nvidia-smi -L

export DATASET_DIR="/data/coco2017"
export TORCH_HOME="/data/torchvision"

declare -a CMD
CMD=('python' '-u' '-m' 'bind_launch' "--nsockets_per_node=${DGXNSOCKET}" \
               "--ncores_per_socket=${DGXSOCKETCORES}" "--nproc_per_node=${DGXNGPU}" )

# run training
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
  --evaluation 5 10 15 20 25 30 35 40 50 55 60 65 70 75 80 85
  --no-save
  --threshold=${SSD_THRESHOLD}
  --data ${DATASET_DIR}
  ${EXTRA_PARAMS})

declare -a pids

trap "date; echo failed :(; exit 1" ERR

for gpu in $(echo "$ALL_GPUS"); do
    export NVIDIA_VISIBLE_DEVICES=$gpu
    nvidia-smi -L
    dest=/tmp/ssd_$(echo $gpu | sed 's|/|_|g').log

    echo "${CMD[@]} ${ARGS[@]} ===> $dest"
    "${CMD[@]}" "${ARGS[@]}" > "$dest" &
    pids+=($!)
done

echo "$(date): starting waiting for $NB_GPU executions: ${pids[@]}"

wait

echo "$(date): done waiting for $NB_GPU executions"

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
echo "ALL FINISHED"
