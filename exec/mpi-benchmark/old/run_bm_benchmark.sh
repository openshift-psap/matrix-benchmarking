#! /bin/bash

set -e


MPIRUN_CMD="mpirun --report-child-jobs-separately --bind-to none --allow-run-as-root --mca btl ^openib -mca pml ob1 --mca btl_tcp_if_include enp1s0f1"

OSU_PATH=/data/kevin/baremetal/osu-micro-benchmarks/mpi

NETWORKS="baremetal"
NET_NAMES="bandwidth latency"
NB_NETWORK_RUN=5
NB_P2P_RUN=3

A2A_NAMES="osu-alltoall osu-allreduce"
NB_A2A_RUN=5
A2A_NB_NODES="4 8 12 16 20 25 28 32"

SYS_NAMES="sys-fio_cephfs sys-fio_local" # sys-cpu
SYS_NB_THREADS="2 4 8"
NB_SYS_RUN=3

LAST_WORKER=7

LINPACK_PLATFORMS="baremetal podman podman_no-seccomp"
LINPACK_THREADS=$(seq 8)

do_benchmark() {
    name="$1"
    src_node="$2"
    dst_node="$3"
    dest="$4"

    if [ $name == "latency" ]; then
        osu_bin="osu_latency";
    else
        osu_bin="osu_bw"
    fi

    tmp_hostfile=$(mktemp /tmp/hostfile.XXXXXX)
    cat > $tmp_hostfile<<EOF
$src_node slots=1
$dst_node slots=1
EOF
    tmp_stdout=$(mktemp /tmp/stdout.XXXXXX)
    $MPIRUN_CMD -np 2 --hostfile $tmp_hostfile $OSU_PATH/pt2pt/$osu_bin | tee $tmp_stdout
    rm $tmp_hostfile
    mv $tmp_stdout $dest
}

run_linpack_benchmark() {
    platform=$1
    threads=$2

    DIR=linpack
    mkdir -p "$DIR"
    dest="$DIR/bm_${platform}.${threads}threads"

    if [ -e $dest ]; then
        echo $dest already recorded
        return
    fi
    echo "Running linpack on $platform with $threads threads > $dest"

    node_id=1

    NODES=$(cat hostfile.all | grep -v '^#' | grep slots | cut -d" " -f1)
    node=$(echo $NODES | cut -d' ' -f$node_id)
    tmp_hostfile=$(mktemp /tmp/hostfile.XXXXXX)
    cat > $tmp_hostfile<<EOF
$node slots=1
EOF

    # prepare from:
    # http://registrationcenter.intel.com/irc_nas/7615/l_lpk_p_11.3.0.004.tgz
    # --> compilers_and_libraries_2016.0.038/linux/mkl/benchmarks/linpack/runme_xeon64
    # --> compilers_and_libraries_2016.0.038/linux/mkl/benchmarks/linpack/
    BENCH_DIR="/mnt/cephfs/kevin/linpack"

    cat > $BENCH_DIR/lininput_xeon64 <<EOF
Sample Intel(R) Optimized LINPACK Benchmark data file (lininput_xeon64)
Intel(R) Optimized LINPACK Benchmark data
1 # number of tests
20000 # problem sizes
20016 # leading dimensions
1 # times to run a test
4 # alignment values (in KBytes)
EOF

    if [ ! -e "$BENCH_DIR/runme_xeon64" ]; then
        echo "ERROR: $BENCH_DIR/runme_xeon64 not found ..."
        exit 1
    fi

    CMD="export OMP_NUM_THREADS=$threads; cd $BENCH_DIR && cat ./lininput_xeon64 && ./runme_xeon64"

    if [[ "$platform" == "podman" || "$platform" == "podman_no-seccomp" ]]; then
        PODMAN="podman run --rm --env-host -v $BENCH_DIR:$BENCH_DIR --userns=keep-id --net=host --pid=host --ipc=host "
        if [ "$platform" == "podman_no-seccomp" ]; then
            PODMAN="$PODMAN --security-opt seccomp=unconfined"
        fi
        PODMAN="$PODMAN quay.io/kpouget/specfem"
    else
        PODMAN=""
    fi

     $MPIRUN_CMD -np 1 --hostfile "$tmp_hostfile" $PODMAN bash -c "$CMD" | tee "$dest"

    set +x

    rm "$tmp_hostfile"
}

run_sys_benchmark() {
    name=$1
    node_id=$2
    threads=$3
    run=$4

    DIR=$(echo $name | sed 's+-+/+')
    mkdir -p "$DIR"
    dest="$DIR/bm_$name.worker0${node_id}_${threads}threads.$run"

    if [ -e $dest ]; then
        echo $dest already recorded
        return
    fi
    echo "Running $name on $nodes nodes and $threads threads run $run/$NB_SYS_RUN > $dest"
    set -x
    NODES=$(cat hostfile.all | grep -v '^#' | grep slots | cut -d" " -f1)
    node=$(echo $NODES | cut -d' ' -f$node_id)
    tmp_hostfile=$(mktemp /tmp/hostfile.XXXXXX)
    cat > $tmp_hostfile<<EOF
$node slots=1
EOF

    if [ "$name" == "sys-cpu" ]; then
        CMD="sysbench --cpu-max-prime=20000 --threads=$threads cpu run"
    else
        if [ "$name" == "sys-fio_cephfs" ]; then
            BENCH_DIR="/mnt/cephfs"
        else
            BENCH_DIR="/data/kpouget"
        fi

        CMD="mkdir -p $BENCH_DIR && cd $BENCH_DIR"
        for mode in rndwr rndrd; do
            CMD="$CMD && sysbench fileio prepare --file-test-mode=$mode >/dev/null"
            CMD="$CMD && sysbench fileio run --file-test-mode=$mode"
        done
    fi

    $MPIRUN_CMD -np 1 --hostfile "$tmp_hostfile" bash -c "$CMD" | tee "$dest"

    rm "$tmp_hostfile"
}

run_network_benchmark() {
    name="$1"
    network="$2"
    run="$3"

    mkdir -p net/net
    dest=net/net/$name.$network.$run

    if [ -e $dest ]; then
        echo $dest already recorded
        return
    fi

    echo "Running $name $network run $run/$NB_NETWORK_RUN into $dest"

    SRC_NODE=bm-worker00
    DST_NODE=bm-worker01
    do_benchmark $name $SRC_NODE $DST_NODE $dest

    echo "Done with $name $network run $run"
}

run_p2p_benchmark() {
    name="$1"
    src_node_id="$2"
    dst_node_id="$3"
    run="$4"

    mkdir -p net/p2p
    dest=net/p2p/$name.worker$src_node_id-$dst_node_id.baremetal.$run
    dest_rev=net/p2p/$name.worker$dst_node_id-$src_node_id.baremetal.$run
    if [ -e $dest ]; then
        echo "$dest already recorded"
        return
    fi

    if [ -e $dest_rev ]; then
        echo "$dest_rev (reverse) already recorded"
        return
    fi


    src_node=$(cat hostfile.all | head -$src_node_id | tail -1 | cut -d' ' -f1)
    dst_node=$(cat hostfile.all | head -$dst_node_id | tail -1 | cut -d' ' -f1)

    echo "Benchmark $name between node #$src_node_id ($src_node) and node #$dst_node_id ($dst_node), run #$run/$NB_P2P_RUN > $dest"

    do_benchmark $name $src_node $dst_node $dest
}

run_osu_collective_benchmark() {
    name="$1"
    network="$2"
    nb_nodes="$3"
    run="$4"

    DIR=$(echo $name | sed 's+-+/+')
    mkdir -p "$DIR"
    dest="$DIR/bm_$name.$network.${nb_nodes}nodes.$run"

    if [ -e $dest ]; then
        echo $dest already recorded
        return
    fi
    echo "Running $name on $network with $nb_nodes nodes run $run/$NB_A2A_RUN > $dest"

    if [ $name == "osu-allreduce" ]; then
        osu_bin="osu_allreduce";
    else
        osu_bin="osu_alltoall"
    fi

    tmp_stdout=$(mktemp /tmp/stdout.XXXXXX)
    $MPIRUN_CMD -np $nb_nodes --hostfile ./hostfile.all $OSU_PATH/collective/$osu_bin | tee $tmp_stdout
    mv $tmp_stdout $dest
}

do_net_benchmark() {
    for run in $(seq $NB_NETWORK_RUN); do
        for name in $NET_NAMES; do
            for network in $NETWORKS; do
                run_network_benchmark $name $network $run
            done
        done
    done
}

do_p2p_benchmark() {
    for name in $NET_NAMES; do
        for start in 1; do
            for stop in $(seq 32 | tail -13); do
                for run in $(seq $NB_P2P_RUN); do
                    [ "$start" == "$stop" ] && continue
                    run_p2p_benchmark $name $start $stop $run
                done
            done
        done
    done
}

do_sys_benchmark() {
    for name in $SYS_NAMES; do
        if [ $name == "sys-cpu" ]; then
            for run in $(seq $NB_SYS_RUN); do
                for threads in $SYS_NB_THREADS; do
                    for node_id in 0 $(seq $LAST_WORKER); do
                        run_sys_benchmark $name $node_id $threads $run
                    done
                done
            done
        else
            for run in $(seq $NB_SYS_RUN); do
                for node_id in 0 $(seq $LAST_WORKER); do
                    run_sys_benchmark $name $node_id 1 $run
                done
            done
        fi
    done
}

do_osu_collective_benchmark() {
    for name in $A2A_NAMES; do
        for run in $(seq $NB_A2A_RUN); do
            for nb_nodes in $A2A_NB_NODES; do
                for network in $NETWORKS; do
                    run_osu_collective_benchmark $name $network $nb_nodes $run
                done
            done
        done
    done
}

do_linpack_benchmark() {
    for platform in $LINPACK_PLATFORMS; do
        for threads in $LINPACK_THREADS; do
            run_linpack_benchmark $platform $threads
        done
    done
}

#do_net_benchmark
#do_p2p_benchmark
#do_sys_benchmark
do_osu_collective_benchmark
#do_linpack_benchmark
