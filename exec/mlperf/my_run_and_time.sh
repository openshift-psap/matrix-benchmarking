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

set -e
set -o pipefail
set -o nounset

cat <<EOF > /dev/null
Environments variables expected from the Pod Spec:

- BENCHMARK=${BENCHMARK:-}

  - "ssd"      Run the SSD benchmark
  - "maskrcnn" Run the MaskRCNN benchmark

- EXECUTION_MODE=${EXECUTION_MODE:-}

  - "fast" Adds target-threshold evaluation points
  - "dry"  Echo the command that would be executed
  - "run"  Normal execution

- DGXSOCKETCORES=${DGXSOCKETCORES:-}

  Number of '--ncores_per_socket' passed to 'bind_launch'. Default: 16

- RUN_DESCR=${RUN_DESCR:-}

  Text description of the execution being executed.
  Example: "GPU: 1 x 1g.5gb x 56 Pods"

- SYNC_IDENTIFIER=${SYNC_IDENTIFIER:-}

  Synchronization unique identifier, shared by all the Job Pods that should start synchronously.
  Example: "2021-12-09_13-55-56"

- SYNC_COUNTER=${SYNC_COUNTER:-}
  Number of Pod expected to start synchronously.
  Example: "56"

- NO_SYNC=${NO_SYNC:-}

  - 'y' if the Pod execution should NOT be synchronized
  - 'n' if the Pod execution should be synchronized

- GPU_COUNT=${GPU_COUNT:-}

  Number of GPUs that should be received. The execution will fail if the number of GPUs actually received is different.
  If GPU_COUNT is 0, the execution stops (successfully) after printing the list of available GPUs.

- GPU_RES_TYPE=${GPU_RES_TYPE:-}

  Value of the GPU resource type requested to Kubernetes
  Example: "nvidia.com/gpus"
  Example: "nvidia.com/mig-1g.5gb"

- GPU_TYPE=${GPU_TYPE:-}

  Type of the MIG resources being benchmarked
  Example: "full"
  Example: "7g.40gb"
  Example: "2g.10gb,3g.20gb"


- SSD_THRESHOLD=${SSD_THRESHOLD:-}

  Value of the '--threshold' parameter passed to SSD.


EOF

echo "8<--8<--8<--8<--"

nvidia-smi -L

echo "8<--8<--8<--8<--"

set -x

NB_GPUS=$(nvidia-smi -L | grep "UUID: MIG-" | wc -l || true)
if [[ "$NB_GPUS" == 0 ]]; then
    # Full GPUs
    ALL_GPUS=$(nvidia-smi -L | grep "UUID: GPU" | cut -d" " -f6 | cut -d')' -f1)
    NB_GPUS=$(nvidia-smi -L | grep "UUID: GPU" | wc -l)
    MIG_MODE=0

    if [[ "$GPU_TYPE" != "full" ]]; then
        echo "FATAL: Expected MIG GPUs, got full GPUs ..."
        exit 1
    fi

    echo "No MIG GPU available, using the full GPUs ($ALL_GPUS)."
else
    # MIG GPUs
    ALL_GPUS=$(nvidia-smi -L | grep "UUID: MIG-" | awk '{ printf $6"\n"}' | cut -d')' -f1)
    MIG_MODE=1

    if [[ "$GPU_TYPE" == "full" ]]; then
        echo "FATAL: Expected full GPUs, got MIG GPUs ..."
        exit 1
    fi

    echo "Found $NB_GPUS MIG instances: $ALL_GPUS"
fi

if [[ $GPU_COUNT == 0 ]]; then
    echo "0 GPU requested. Exiting now."
    echo "ALL FINISHED"

    exit 0
elif [[ $NB_GPUS != $GPU_COUNT ]]; then
    echo "FATAL: Expected $GPU_COUNT GPUs, got $NB_GPUS"
    exit 1
fi

# start timing
start=$(date +%s)
start_fmt=$(date +%Y-%m-%d\ %r)
echo "STARTING TIMING RUN AT $start_fmt $RUN_DESCR"

# run benchmark
set -x

export NCCL_DEBUG=INFO

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

# setup the training

if [[ "${BENCHMARK:-}" == "maskrcnn" ]]; then
    echo "Setting up the Mask RCNN benchmark..."

    NEXP=1

    # DGX A100 config
    source config_DSS8440x8A100-PCIE-40GB.sh

fi

DGXNSOCKET=1
DGXSOCKETCORES=${DGXSOCKETCORES:-16}

if [[ $MIG_MODE == "1" ]]; then
   DGXNGPU=1
   echo "Running in parallel mode."

else
    DGXNGPU=$NB_GPUS
    echo "Running in multi-gpu mode."
fi



declare -a CMD
CMD=('python' '-u' '-m' 'bind_launch' "--nsockets_per_node=${DGXNSOCKET}" \
              "--ncores_per_socket=${DGXSOCKETCORES}" "--nproc_per_node=${DGXNGPU}" )

declare -a ARGS

echo "Patching 'bind_launch.py' to err-exit on failure ..."
sed 's/process.wait()$/if process.wait(): sys.exit(1)/' -i bind_launch.py

if [[ "${BENCHMARK:-}" == "ssd" ]]; then
    echo "Setting up the SSD benchmark..."

    # prepare the DGXA100-specific configuration (config_DGXA100.sh)
    EXTRA_PARAMS='--batch-size=114 --warmup=650 --lr=3.2e-3 --wd=1.3e-4'

    NUMEPOCHS=${NUMEPOCHS:-80}

    ARGS=(train.py
          --use-fp16
          --nhwc
          --pad-input
          --jit
          --delay-allreduce
          --opt-loss
          --epochs "${NUMEPOCHS}"
          --warmup-factor 0
          --no-save
          --threshold=${SSD_THRESHOLD}
          --data ${DATASET_DIR}
          ${EXTRA_PARAMS})

    if [[ "$EXECUTION_MODE" == "fast" ]]; then
        echo "Running in FAST mode"
        ARGS+=(--evaluation 5 10 15 20 25 30 35 40 50 55 60 65 70 75 80 85)
    fi

elif [[ "${BENCHMARK:-}" == "maskrcnn" ]]; then
    echo "Setting up the Mask RCNN benchmark..."

    sed 's/torch.set_num_threads(1)$/import time, sys; time.sleep(int(sys.argv[1].split("=")[-1]));torch.set_num_threads(1);/' -i tools/train_mlperf.py
    #sed 's/fwd_graph.capture_/pass # cannot call fwd_graph.capture_/' -i function.py
    #sed 's/bwd_graph.capture_/pass # cannot call bwd_graph.capture_/' -i function.py

    MODEL="$DATASET_DIR/models/R-50.pkl"
    if [[ -f "$MODEL" ]]; then
        sum=$(cat $MODEL | md5sum)
        if [[ "$sum" != "6652b4a9c782d82bb3d42118be74d79b  -" ]]; then
            echo "Wrong checksum, deleting the model ..."
            rm "$MODEL"
        fi
    fi
    if [[ ! -f "$MODEL" ]]; then
        mkdir -p $(dirname "$MODEL")
        curl --silent https://dl.fbaipublicfiles.com/detectron2/ImageNetPretrained/MSRA/R-50.pkl > $MODEL
    fi

    ln -sf $DATASET_DIR /coco

    # COCO_PKL="$DATASET_DIR/instances_train2017.json.pickled"
    # if [[ ! -f "$COCO_PKL" ]]; then
    #     python3 pickle_coco_annotations.py \
    #             --root "$DATASET_DIR" \
    #             --ann "$DATASET_DIR/annotations/instances_train2017.json" \
    #             --pickle_output_file "$COCO_PKL"
    # fi
    # ln -s /data/coco2017/ /pkl_coco

    ARGS=(tools/train_mlperf.py
          ${EXTRA_PARAMS}
          --config-file 'configs/e2e_mask_rcnn_R_50_FPN_1x.yaml'
          DTYPE 'float16'
          PATHS_CATALOG 'maskrcnn_benchmark/config/paths_catalog_dbcluster.py'
          MODEL.WEIGHT "$MODEL"
          DISABLE_REDUCED_LOGGING True
          ${EXTRA_CONFIG}
         )

else
    echo "FATAL: unknown benchmark: '${BENCHMARK:-}'"
    exit 1
fi

if [[ "$EXECUTION_MODE" == "dry" ]]; then
    echo "Running in DRY mode"
    CMD[0]="echo"
fi

trap "date; echo failed; exit 1" ERR

if [[ "$NO_SYNC" != "y" ]]; then
    SYNC_DIR=$DATASET_DIR/sync

    mkdir -p "$SYNC_DIR"

    for sync_f in "$SYNC_DIR/"*; do
        if [[ "$sync_f" != "$DATASET_DIR/sync/$SYNC_IDENTIFIER" ]]; then
            rm -f "$sync_f"
        fi
    done

    set +x
    echo "$(date) Waiting for all the $SYNC_COUNTER Pods to start ..."
    touch "$DATASET_DIR/sync/$SYNC_IDENTIFIER"

    while true; do
        if ! grep --silent $HOSTNAME "$DATASET_DIR/sync/$SYNC_IDENTIFIER"; then
            echo "Adding $HOSTNAME to the sync file ..."
            echo $HOSTNAME >> "$DATASET_DIR/sync/$SYNC_IDENTIFIER"
        fi

        cnt=$(cat "$DATASET_DIR/sync/$SYNC_IDENTIFIER" | wc -l)
        [[ $cnt == "$SYNC_COUNTER" ]] && break
        echo "$HOSTNAME Found $cnt Pods, waiting to have $SYNC_COUNTER ..."
        nl "$DATASET_DIR/sync/$SYNC_IDENTIFIER"
        sleep 5
    done
    echo "$(date) All the $SYNC_COUNTER Pods are running, launch the GPU workload."
    set -x
else
    echo "Pod startup synchronization disabled, do not wait for $SYNC_COUNTER Pods ..."
fi

nvidia-smi -L

# run the training

if [[ $MIG_MODE == 1 && $NB_GPUS != 1 ]]; then
    declare -a pids

    for gpu in $(echo "$ALL_GPUS"); do
        export NVIDIA_VISIBLE_DEVICES=$gpu
        export CUDA_VISIBLE_DEVICES=$gpu

        dest=/tmp/benchmark_$(echo $gpu | sed 's|/|_|g').log

        # run training
        "${CMD[@]}" "${ARGS[@]}" >"$dest" 2>"$dest.stderr" &
        pids+=($!)
        echo "Running on $gpu ===> $dest: PID $!"
    done
    echo "$(date): waiting for parallel $NB_GPUS executions: ${pids[@]}"
    for pid in ${pids[@]};
    do
        wait $pid;
    done
else
    dest=/tmp/benchmark_all.log
    if [[ $MIG_MODE == 1 ]]; then
        echo "Running on the MIG GPU"
    else
        echo "Running on all the $NB_GPUS GPUs "
    fi

    "${CMD[@]}" "${ARGS[@]}" | tee -a "$dest"
fi

if [[ "$EXECUTION_MODE" == "dry" ]]; then
    echo "Running in DRY mode, sleep 2min"
    sleep 2m
fi

echo "$(date): done waiting for $NB_GPUS executions"

ls /tmp/benchmark_*
grep . /tmp/benchmark_*.log

# end timing
end=$(date +%s)
end_fmt=$(date +%Y-%m-%d\ %r)
echo "START TIMING RUN WAS $start_fmt"
echo "ENDING TIMING RUN AT $end_fmt"

nvidia-smi -L

# report result
result=$(($end - $start))
if [[ "${BENCHMARK:-}" == "ssd" ]]; then
    result_name="SINGLE_STAGE_DETECTOR"

elif [[ "${BENCHMARK:-}" == "maskrcnn" ]]; then
    result_name="OBJECT_DETECTION"

else
    result_name="(can't be reached)"
fi

echo "RESULT,$result_name,,$result,nvidia,$start_fmt"
echo "ALL FINISHED $RUN_DESCR"
