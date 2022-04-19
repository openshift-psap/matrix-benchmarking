# oc apply -f https://raw.githubusercontent.com/kubeflow/mpi-operator/v0.3.0/deploy/v2beta1/mpi-operator.yaml
# oc set image -n mpi-operator deployment.apps/mpi-operator mpi-operator=docker.io/mpioperator/mpi-operator:0.3.0

oc apply -f https://raw.githubusercontent.com/volcano-sh/volcano/master/installer/volcano-development.yaml

oc new-project mpi-benchmark
oc adm policy add-scc-to-user privileged -z default
oc adm policy add-scc-to-user anyuid -z  default

oc apply -f 001_imagestream.yaml
oc apply -f 002_base_image.buildconfig.yaml
oc apply -f 003_osu-bench.buildconfig.yaml
