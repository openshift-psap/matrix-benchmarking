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

DGXNGPU=$(nvidia-smi -L | grep "UUID: MIG-GPU" | wc -l)
if [[ "$DGXNGPU" == 0 ]]; then
    DGXNGPU=$(nvidia-smi -L | grep "UUID: GPU" | wc -l)
    echo "No MIG GPU available, using the GPUs."
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
if [ -n "${SLURM_LOCALID-}" ]; then
  # Mode 1: Slurm launched a task for each GPU and set some envvars; no need for parallel launch
  if [ "${SLURM_NTASKS}" -gt "${SLURM_JOB_NUM_NODES}" ]; then
    CMD=( './bind.sh' '--' 'python' '-u' )
  else
    CMD=( 'python' '-u' )
  fi
else
  # Mode 2: Single-node Docker; need to launch tasks with Pytorch's distributed launch
  # TODO: use bind.sh instead of bind_launch.py
  #       torch.distributed.launch only accepts Python programs (not bash scripts) to exec
  CMD=( 'python' '-u' '-m' 'bind_launch' "--nsockets_per_node=${DGXNSOCKET}" \
    "--ncores_per_socket=${DGXSOCKETCORES}" "--nproc_per_node=${DGXNGPU}" )
fi

# run training
"${CMD[@]}" train.py \
  --use-fp16 \
  --nhwc \
  --pad-input \
  --jit \
  --delay-allreduce \
  --opt-loss \
  --epochs "${NUMEPOCHS}" \
  --warmup-factor 0 \
  --no-save \
  --threshold=${SSD_THRESHOLD} \
  --data ${DATASET_DIR} \
  ${EXTRA_PARAMS} ; ret_code=$?

[[ $ret_code != 0 ]] && exit $ret_code

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
