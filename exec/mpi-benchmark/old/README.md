Quick and Dirty MPI benchmark for OpenShift
===========================================

Using `osu-micro-benchmarks-5.6.3` benchmark.

1. Create the base images

```
oc create -f bc_mpi_base_image.yaml
oc create -f bc_osu-bench-image.yaml
```

2. Customize `apply_template.go` and `mpijob_template.yaml` as you
need to prepare various benchmark configurations, and test with this
command:

```
name=bandwidth
net=Multus
go run apply_template.go -name $name -net $net | oc create -f- 
```

3. Customize `run_benchmark.sh` as you need and run it

4. Install plotly to plot the benchmark results

```
pip install plotly==4.6.0
```

5. Plot the benchmark results:

```
./plot.py logs/bandwidth* 
./plot.py logs/latency* 
```

6. Sample outputs:

(multus and baremetal overlap)

![latency](graph/latency.png)
![bandwidth](graph/bandwidth.png)

Troubleshooting
---------------

* For the `hostNetwork` to work, you need to allow in in the `SecurityContextConstraints`:
```
oc patch scc restricted --type=merge -p '{"allowHostNetwork": true}'
```
