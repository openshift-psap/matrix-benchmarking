#!/bin/bash

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

export INSLURM=0;
export NEXP=1;
export DATADIR=/data/coco2017;
export LOGDIR=/data;

DGX_SYSTEM=${DGX_SYSTEM:-"DGX1"}
if [[ ! -f config_${DGX_SYSTEM}.sh ]]; then
  echo "Unknown DGX system"
  exit 1
fi
echo "Loading config_${DGX_SYSTEM}.sh"
source config_${DGX_SYSTEM}.sh

SLURM_NTASKS_PER_NODE=${SLURM_NTASKS_PER_NODE:-$DGX_NGPU}
SLURM_JOB_ID=${SLURM_JOB_ID:-$RANDOM}
MULTI_NODE=${MULTI_NODE:-''}

echo "Run vars: jobid $SLURM_JOB_ID gpus $SLURM_NTASKS_PER_NODE mparams $MULTI_NODE"

# runs benchmark and reports time to convergence
# to use the script:
#   run_and_time.sh
export NCCL_DEBUG=INFO

set -e

# start timing
start=$(date +%s)
start_fmt=$(date +%Y-%m-%d\ %r)
echo "STARTING TIMING RUN AT $start_fmt"

# run benchmark
NUM_EPOCHS=${NUM_EPOCHS:-80}

echo "running benchmark with MIG GPUs"
nvidia-smi -L

export DATASET_DIR="/data/coco2017"
export TORCH_MODEL_ZOO="/data/torchvision"

# run training
python3 -m bind_launch  \
  --nsockets_per_node ${DGX_NSOCKET} \
  --ncores_per_socket ${DGX_SOCKET_CORES} \
  --nproc_per_node $SLURM_NTASKS_PER_NODE $MULTI_NODE \
      train.py \
        --use-fp16 \
        --nhwc \
        --pad-input \
        --jit \
        --delay-allreduce \
        --opt-loss \
        --epochs "${NUM_EPOCHS}" \
        --warmup-factor 0 \
        --no-save \
        --threshold=0.23 \
        --data ${DATASET_DIR} \
        --evaluation 120000 160000 180000 200000 220000 240000 260000 280000 \
        ${EXTRA_PARAMS[@]} ; ret_code=$?

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
#
