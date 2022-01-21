#! /bin/bash

set -e

NETWORKS="SDN Multus HostNetwork"

NET_NAMES="bandwidth latency"
NB_NETWORK_RUN=5
NB_P2P_RUN=2

A2A_NAMES="osu-allreduce osu-alltoall"
NB_A2A_RUN=5
A2A_NB_NODES="4 8 12 16 20 25 28 32"

SYS_NAMES="sys-fio_cephfs" # sys-cpu sys-fio_cephfs sys-fio_local
SYS_NB_THREADS="2 4 8"
NB_SYS_RUN=5

LAST_WORKER=7

do_net_benchmark() {
    name="$1"
    network="$2"
    dest="$3"
    if [ "$#" -gt 3 ]; then
        src_node="$4"
        dst_node="$5"

        nodes="-src $src_node -dst $dst_node"
    else
        nodes=""
    fi
    cmd="-net $network $nodes"

    do_benchmark "$name" "$cmd" "$dest"
}

do_benchmark() {
    name="$1"
    cmd="$2"
    dest="$3"

    echo "Create -name $name $cmd"
    echo
    return

    go run apply_template.go -name "$name" $cmd | oc delete -f- 2>/dev/null >/dev/null || echo -n

    create=$(go run apply_template.go -name "$name" $cmd \
           | oc create -f- | tail -1) # mpijob.kubeflow.org/bandwidth-multus-2procs created

    mpijob_name=$(echo $create | grep mpijob | tail -1 | cut -d' ' -f1 | cut -d"/" -f2) # bandwidth-multus-2procs

    echo "Waiting for mpijob/$mpijob_name launcher pod to run $dest ..."

    prev_status=""
    cnt=0
    while true; do
        launcher_status=$(oc get pods -l mpi_job_name=$mpijob_name,mpi_role_type=launcher --no-headers \
                            | awk '{ print $1 " " $3 }')
        launcher_pod_name=$(echo "$launcher_status" | cut -d' ' -f1)
        pod_status=$(echo "$launcher_status" | cut -d' ' -f2)
        if [ "$pod_status" != "$prev_status" ]; then
            echo "$launcher_pod_name is $pod_status ... (${cnt}s)"
        fi

        if [ "$pod_status" == "Completed" ]; then
            break
        fi

        cnt=$(expr $cnt + 1)
        if [ "$cnt" -gt 90 ];
        then
           echo "Timeout ..."
           break
        fi
        sleep 1
    done

    if ! [ "$cnt" -gt 90 ];
    then
       oc logs pod/$launcher_pod_name | grep -v '^+' | grep -v '^\[' > $dest
    else
        echo TIMEOUT > $dest
    fi

    create=$(go run apply_template.go -name "$name" $cmd \
           | oc delete -f-)
}

run_sys_benchmark() {
    name="$1"
    node_id="$2"
    threads="$3"
    run="$4"

    DIR=$(echo $name | sed 's+-+/+')
    mkdir -p "$DIR"
    dest="$DIR/oc_$name.worker0${node_id}_${threads}threads.$run"

    if [ -e $dest ]; then
        echo $dest already recorded
        return
    fi
    echo "Running $name on $nodes nodes and $threads threads run $run/$NB_CPU_RUN > $dest"

    node="worker0$node_id"
    cmd="-src $node -threads $threads"
    #oc label node/$node "kpouget.benchmark=$node" --overwrite
    do_benchmark "$name" "$cmd" "$dest"
}

run_network_benchmark() {
    name="$1"
    network="$2"
    run="$3"

    mkdir -p logs
    dest=net/net/$name.$network.$run

    if [ -e $dest ]; then
        echo $dest already recorded
        return
    fi

    echo "Benchmark $name $network run #$run/$NB_NETWORK_RUN"

    do_net_benchmark "$name" "$network" "$dest"
}

run_p2p_benchmark() {
    name="$1"
    network="$2"
    src_node_id="$3"
    dst_node_id="$4"
    run="$5"

    mkdir -p p2p
    dest=p2p/$name.worker$src_node_id-$dst_node_id.$network.$run
    dest_rev=p2p/$name.worker$dst_node_id-$src_node_id.$run
    if [ -e $dest ]; then
        echo "$dest already recorded"
        return
    fi

    if [ -e $dest_rev ]; then
        echo "$dest_rev (reverse) already recorded"
        return
    fi

    src_node=worker0$src_node_id
    dst_node=worker0$dst_node_id
    #oc label node/$src_node node/$dst_node  "kpouget.benchmark=$src_node-$dst_node" --overwrite

    echo "Benchmark $name/$network between $src_node and $dst_node, run #$run/$NB_P2P_RUN"

    do_net_benchmark $name $network $dest $src_node $dst_node
}

run_osu_collective_benchmark() {
    name="$1"
    network="$2"
    nb_nodes="$3"
    run="$4"

    DIR=$(echo $name | sed 's+-+/+')
    mkdir -p "$DIR"
    dest="$DIR/oc_$name.$network.${nb_nodes}nodes.$run"

    if [ -e $dest ]; then
        echo $dest already recorded
        return
    fi
    echo "Running $name on $network with $nb_nodes nodes run $run/$NB_A2A_RUN > $dest"

    cmd="-np $nb_nodes -net $network"
    do_benchmark "$name" "$cmd" "$dest"
}

do_network_benchmark() {
    for run in $(seq $NB_NETWORK_RUN); do
        for name in $NET_NAMES; do
            for network in $NETWORKS; do
                run_network_benchmark $name $network $run
            done
        done
    done
}

do_p2p_benchmark() {
    for src_node_id in 0 $(seq $LAST_WORKER); do
        for dst_node_id in 0 $(seq $LAST_WORKER); do
            for run in $(seq $NB_P2P_RUN); do
                for name in $NET_NAMES; do
                    for network in $NETWORKS; do
                        [ "$src_node_id" == "$dst_node_id" ] && continue
                        run_p2p_benchmark $name $network $src_node_id $dst_node_id $run
                    done
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

#do_network_benchmark
do_p2p_benchmark
#do_sys_benchmark
#do_osu_collective_benchmark
