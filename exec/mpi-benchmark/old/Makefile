cpu:
	./plot_cpu_stdev.py sys/cpu/*

fio:
	./plot_fio_stdev.py sys/fio*/*

fio_local:
	./plot_fio_stdev.py $$(ls sys/fio*/* | grep -v ceph)

net_net_bw:
	./plot_net_stdev.py net/net/bandwidth*

net_net_lat:
	./plot_net_stdev.py net/net/latency*

net_p2p_bw:
	./plot_net_stdev.py net/p2p/bandwidth*

net_p2p_lat:
	./plot_net_stdev.py net/p2p/latency*

net_a2a_allreduce:
	./plot_net_stdev.py osu/allreduce/*.*

net_a2a_allreduce_20:
	./plot_net_stdev.py osu/allreduce/*20nodes*

net_a2a_alltoall:
	./plot_net_stdev.py osu/alltoall/*.*

net_a2a_alltoall_20:
	./plot_net_stdev.py osu/alltoall/*20nodes*

linpack:
	./plot_linpack_stdev.py linpack/*

.PHONY: linpack
