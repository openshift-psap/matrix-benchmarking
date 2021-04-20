#! /bin/bash

#GPU_NODES=$(oc get nodes -lnvidia.com/gpu.present=true --no-headers -oname)
GPU_NODES=node/perf23-nva100

for gpu_node in $(echo $GPU_NODES); do
    in_alloc=0
    in_capacity=0
    in_labels=0
    descr="$(oc describe $gpu_node)"

    while read line; do
        if [[ "$line" == "Labels:"* ]]; then
            in_labels=1
            echo "nvidia.com/* labels of $gpu_node:"

            line=$(echo "$line" | sed s/Labels://)
        elif [[ "$line" == "Capacity:" ]]; then
            in_capacity=1
            echo
            echo "nvidia.com/* capacity of $gpu_node:"
        elif [[ "$line" == "Allocatable:" ]]; then
            in_alloc=1
            in_capacity=0
            echo
            echo "nvidia.com/* allocatable of $gpu_node:"
        fi

        if [ $in_labels == 1 ]; then
            if [[ "$line" == "Annotations:"* ]]; then
                in_labels=0
                continue
            fi
            [[ "$line" != *"nvidia.com/"* ]] && continue

            [[ "$line" != *".count="* ]] && \
                [[ "$line" != *".product="* ]] && \
                [[ "$line" != *".memory="* ]] && \
                [[ "$line" != *".strategy="* ]] && \
                [[ "$line" != *".slices."* ]] && continue

            echo "  $line"

        elif [ $in_alloc == 1 ]; then
            if [[ "$line" == "System"* ]]; then
                in_alloc=0
                continue
            fi
            [[ "$line" == *"nvidia.com/"* ]] && echo "  $line"
        elif [ $in_capacity == 1 ]; then

            [[ "$line" == *"nvidia.com/"* ]] && echo "  $line"
        fi
    done <<< $descr
done
