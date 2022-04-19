apiVersion: kubeflow.org/v2beta1
kind: MPIJob
metadata:
  name: run-bert-squad
spec:
  cleanPodPolicy: Running
  slotsPerWorker: 1
  mpiReplicaSpecs:
    Launcher:
      replicas: 1
      restartPolicy: OnFailure
      template:
        spec:
          initContainers:
          - name: wait-hostfilename
            image: image-registry.openshift-image-registry.svc:5000/matrix-benchmarking/aiml:bert
            command:
            - bash
            - -cx
            - "[[ $(cat /etc/mpi/hostfile | wc -l) != 0 ]] && (date; echo 'Hostfile is ready'; cat /etc/mpi/hostfile) || (date; echo 'Hostfile not ready ...'; sleep 10; exit 1) && while read host; do while ! ssh $host echo $host ; do date; echo \"Pod $host is not up ...\"; sleep 10; done; date; echo \"Pod $host is ready\"; done <<< \"$(cat /etc/mpi/hostfile)\""
            volumeMounts:
            - mountPath: /etc/mpi
              name: mpi-job-config
            - mountPath: /root/.ssh
              name: ssh-auth
          containers:
          - name: worker
            image: image-registry.openshift-image-registry.svc:5000/matrix-benchmarking/aiml:bert
            imagePullPolicy: Always
            env:
            - name: MATBENCH_BATCH_SIZE
              value: 8
            - name: MATBENCH_PRECISION
              value: fp32
            - name: MATBENCH_EXTRA_VARS
              value: # not used at the moment
            command:
            - mpirun
            - --allow-run-as-root
            - -bind-to
            - none
            - -map-by
            - slot
            - -mca
            - pml
            - ob1
            - -mca
            - btl
            - ^openib
            - -x
            - NVIDIA_BUILD_ID
            - -x
            - MATBENCH_BATCH_SIZE
            - -x
            - MATBENCH_PRECISION
            - -x
            - MATBENCH_EXTRA_VARS
            - bash
            - -x
            - /mnt/entrypoint/run-bert-multinode_squad.sh
            securityContext:
              privileged: true
            volumeMounts:
            - mountPath: /workspace/bert_tf2/data/download
              name: storage-volume
            - name: entrypoint
              mountPath: /mnt/entrypoint
          volumes:
          - name: storage-volume
            persistentVolumeClaim:
              claimName: benchmarking-bert-dataset
          - name: entrypoint
            configMap:
              name: bert-entrypoint
    Worker:
      replicas: 16
      restartPolicy: OnFailure
      template:
        spec:
          containers:
            - name: worker
              image: image-registry.openshift-image-registry.svc:5000/matrix-benchmarking/aiml:bert
              imagePullPolicy: Always
              resources:
                limits:
                  nvidia.com/gpu: 1
              securityContext:
                privileged: true
              volumeMounts:
              - mountPath: /workspace/bert_tf2/data/download
                name: storage-volume
              - name: entrypoint
                mountPath: /mnt/entrypoint
          volumes:
          - name: storage-volume
            persistentVolumeClaim:
              claimName: benchmarking-bert-dataset
          - name: entrypoint
            configMap:
              name: bert-entrypoint
