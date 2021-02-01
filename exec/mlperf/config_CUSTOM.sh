#!/bin/bash
## DL params
EXTRA_PARAMS=(
  --batch-size      "120"
  --eval-batch-size "160"
  --warmup          "650"
  --lr              "2.92e-3"
  --wd              "1.6e-4"
  --use-nvjpeg
  --use-roi-decode
)

## System run parms
#DGXNNODES=1
WALLTIME=01:00:00

## System config params
DGX_NGPU=$(nvidia-smi -L | grep UUID)
DGX_SOCKET_CORES=23
DGX_NSOCKET=1
#DGXHT=2         # HT is on is 2, HT off is 1
#DGXIBDEVICES=''
#
