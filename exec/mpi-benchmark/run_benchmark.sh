#! /bin/bash

MODE=...


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
