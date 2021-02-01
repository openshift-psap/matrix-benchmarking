#! /usr/bin/python3
# https://github.com/mlperf/training_results_v0.7/blob/master/NVIDIA/benchmarks/maskrcnn/implementations/pytorch/bind_launch.py
import sys
import subprocess
import os
import socket
from argparse import ArgumentParser, REMAINDER

import torch

def parse_args():
    """
    Helper function parsing the command line options
    @retval ArgumentParser
    """
    parser = ArgumentParser(description="PyTorch distributed training launch "
                                        "helper utilty that will spawn up "
                                        "multiple distributed processes")

    # Optional arguments for the launch helper
    parser.add_argument("--nnodes", type=int, default=1,
                        help="The number of nodes to use for distributed "
                             "training")
    parser.add_argument("--node_rank", type=int, default=0,
                        help="The rank of the node for multi-node distributed "
                             "training")
    parser.add_argument("--nproc_per_node", type=int, default=1,
                        help="The number of processes to launch on each node, "
                             "for GPU training, this is recommended to be set "
                             "to the number of GPUs in your system so that "
                             "each process can be bound to a single GPU.")
    parser.add_argument("--master_addr", default="127.0.0.1", type=str,
                        help="Master node (rank 0)'s address, should be either "
                             "the IP address or the hostname of node 0, for "
                             "single node multi-proc training, the "
                             "--master_addr can simply be 127.0.0.1")
    parser.add_argument("--master_port", default=29500, type=int,
                        help="Master node (rank 0)'s free port that needs to "
                             "be used for communciation during distributed "
                             "training")
    parser.add_argument('--no_hyperthreads', action='store_true',
                        help='Flag to disable binding to hyperthreads')
    parser.add_argument('--no_membind', action='store_true',
                        help='Flag to disable memory binding')

    # non-optional arguments for binding
    parser.add_argument("--nsockets_per_node", type=int, required=True,
                        help="Number of CPU sockets on a node")
    parser.add_argument("--ncores_per_socket", type=int, required=True,
                        help="Number of CPU cores per socket")

    # positional
    parser.add_argument("training_script", type=str,
                        help="The full path to the single GPU training "
                             "program/script to be launched in parallel, "
                             "followed by all the arguments for the "
                             "training script")

    # rest from the training program
    parser.add_argument('training_script_args', nargs=REMAINDER)
    return parser.parse_args()

def main():
    args = parse_args()

    slicing = subprocess.check_output("nvidia-smi -L", shell=True).decode('utf-8')

    mig_uids = [l.split("UUID: ")[1][:-1] for l in slicing.split("\n") if "MIG" in l]
    for i, uid in enumerate(mig_uids):
      print(f"{i} --> {uid}")

    # variables for numactrl binding
    NSOCKETS = args.nsockets_per_node
    NGPUS_PER_SOCKET = 1
    NCORES_PER_GPU = args.ncores_per_socket // len(mig_uids)

    args.nproc_per_node = len(mig_uids)
    # world size in terms of number of processes
    dist_world_size = args.nproc_per_node * args.nnodes

    # set PyTorch distributed related environmental variables
    current_env = os.environ.copy()
    current_env["MASTER_ADDR"] = args.master_addr
    current_env["MASTER_PORT"] = str(args.master_port)
    current_env["WORLD_SIZE"] = str(dist_world_size)

    processes = []

    if args.nproc_per_node != len(mig_uids):
        print(f"Got --nproc_per_node={args.nproc_per_node} and {len(mig_uids)} MIG devices ...")
        print(slicing)
        exit(1)

    for local_rank in range(0, args.nproc_per_node):
        # each process's rank
        dist_rank = args.nproc_per_node * args.node_rank + local_rank
        current_env["RANK"] = str(dist_rank)

        # form numactrl binding command
        cpu_ranges = [local_rank * NCORES_PER_GPU,
                     (local_rank + 1) * NCORES_PER_GPU - 1,
                     local_rank * NCORES_PER_GPU + (NCORES_PER_GPU * NGPUS_PER_SOCKET * NSOCKETS),
                     (local_rank + 1) * NCORES_PER_GPU + (NCORES_PER_GPU * NGPUS_PER_SOCKET * NSOCKETS) - 1]

        numactlargs = []
        if args.no_hyperthreads:
            numactlargs += [ "--physcpubind={}-{}".format(*cpu_ranges[0:2]) ]
        else:
            numactlargs += [ "--physcpubind={}-{},{}-{}".format(*cpu_ranges) ]

        if not args.no_membind:
            memnode = local_rank // NGPUS_PER_SOCKET
            numactlargs += [ "--membind={}".format(memnode) ]

        # spawn the processes
        cmd = [ #"echo",
                "/usr/bin/env", f"CUDA_VISIBLE_DEVICES={mig_uids[local_rank]}",
                "/usr/bin/numactl" ] \
            + numactlargs \
            + [ sys.executable,
                "-u",
                args.training_script,
                "--local_rank=0"
              ] \
            + args.training_script_args
        print("Running:", cmd, file=sys.stderr)

        sys.stdout.flush()
        sys.stderr.flush()

        process = subprocess.Popen(cmd, env=current_env)
        processes.append(process)

    for process in processes:
        process.wait()


if __name__ == "__main__":
    main()
