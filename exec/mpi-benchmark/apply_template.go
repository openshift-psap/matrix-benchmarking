package main

import (
	"bytes"
	"io/ioutil"
	"log"
	"flag"
	"fmt"
	"text/template"
	"strconv"
	"strings"
)

type MpiBenchmarkData struct {
	Bench string
	Name string
	Image string
	Nproc int
	NetworkType string
	Command string
	SrcNode string
	DstNode string
}

type TemplateBase struct {
	Manifests *map[string]string
}

var flag_name = flag.String("name", "", "")
var flag_net = flag.String("net", "", "")
var flag_src = flag.String("src", "", "")
var flag_dst = flag.String("dst", "", "")

var flag_np = flag.String("np", "", "")

var flag_node_id = flag.String("node_id", "", "")
var flag_threads = flag.String("threads", "", "")

var OSU_MPI_PATH = "/opt/osu-micro-benchmarks/libexec/osu-micro-benchmarks/mpi/"
func main() {
	flag.Parse()

	var cmd, name, image string
	var nproc int
	if *flag_name == "" {
		log.Fatal("Please pass a -name value")
	} else if *flag_name == "latency" || *flag_name == "bandwidth" {
		var bin string
		if *flag_name == "bandwidth" {
			bin = "pt2pt/osu_bw"
		} else {
			bin = "pt2pt/osu_latency"
		}
		cmd = OSU_MPI_PATH + bin

		if *flag_net == "" {
			log.Fatal("Please pass a -net value")
		} else if *flag_net != "SDN" && *flag_net != "Multus" && *flag_net != "HostNetwork" {
			log.Fatal("Please pass a valid -net value (SDN, Multus, HostNetwork)")
		}

		if *flag_src == "" || *flag_dst == "" {
			if *flag_src != "" || *flag_dst != "" {
				log.Fatal("Please pass -src AND -dst flags")
			}
		}

		name = *flag_name+"-"+ strings.ToLower(*flag_net)+"-2procs"
		if *flag_src != "" {
			name += "-"+*flag_src+"-"+*flag_dst
		}
		nproc = 2
		image = "image-registry.openshift-image-registry.svc:5000/mpi-benchmark/mpi-bench:osu-bench"
	} else if *flag_name == "sys-cpu" || strings.HasPrefix(*flag_name, "sys-fio_")  {
		if *flag_src == "" {
			log.Fatal("Please pass a valid -src value")
		}
		if *flag_name == "sys-cpu" {
			if *flag_threads == "" {
				log.Fatal("Please pass a valid -thread value")
			}
			cmd = fmt.Sprintf("sysbench --cpu-max-prime=20000 --threads=%s cpu run", *flag_threads)
		} else {
			var dir string
			if *flag_name == "sys-fio_tmp" {
				dir = "/tmp"
			} else if (*flag_name == "sys-fio_local" || *flag_name == "sys-fio_cephfs" || *flag_name == "sys-fio_overlay") {
				dir = "/mnt/storage"
			} else {
				log.Fatalf("Unsuported mode: %s", *flag_name)
			}

			cmd = fmt.Sprintf("mkdir -p %s && cd %s ", dir, dir)

			cmd += "&& sysbench fileio prepare --file-test-mode=rndwr >/dev/null "
			cmd += "&& sysbench fileio run --file-test-mode=rndwr "

			cmd += "&& sysbench fileio prepare --file-test-mode=rndrd >/dev/null "
			cmd += "&& sysbench fileio run --file-test-mode=rndrd "
			cmd += "&& echo DONE"
		}
		name = strings.Replace(*flag_name, "_", "-", -1)+"-"+*flag_src+"-"+*flag_threads+"threads"
		nproc = 1
		image = "image-registry.openshift-image-registry.svc:5000/mpi-benchmark/mpi-bench:base3"
	} else if *flag_name == "osu-allreduce" || *flag_name == "osu-alltoall" {
		var bin string

		name = strings.Replace(*flag_name, "_", "-", -1)+"-"+ strings.ToLower(*flag_net)+"-"+*flag_np+"procs"
		if *flag_name == "osu-allreduce" {
			bin = "collective/osu_allreduce"
		} else {
			bin = "collective/osu_alltoall"
		}
		cmd = OSU_MPI_PATH + bin

		if *flag_np == "" {
			log.Fatal("Please pass -np flag")
		}
		var err error
		nproc, err = strconv.Atoi(*flag_np)
		if err != nil {
			log.Fatalf("Failed to parse '-np %s'", *flag_np, err)
		}

		if *flag_net == "" {
			log.Fatal("Please pass a -net value")
		} else if *flag_net != "SDN" && *flag_net != "Multus" && *flag_net != "HostNetwork" {
			log.Fatal("Please pass a valid -net value (SDN, Multus, HostNetwork)")
		}

		image = "image-registry.openshift-image-registry.svc:5000/mpi-benchmark/mpi-bench:osu-bench"
	} else {
		log.Fatalf("Invalid -name value: '%s'", *flag_name)
	}

	tmpl_data := MpiBenchmarkData{
		Bench: *flag_name,
		Name: name,
		Image: image,
		Nproc: nproc,
		NetworkType: *flag_net,
		Command: cmd,
		SrcNode: *flag_src,
		DstNode: *flag_dst,
	}

	funcMap := template.FuncMap{
        "ToLower": strings.ToLower,
    }

	TEMPLATE_FILE := "mpijob_template.yaml"

	template_doc, err := ioutil.ReadFile(TEMPLATE_FILE)
	if err != nil {
		log.Fatal(fmt.Sprintf("Failed to read the template '%s'", TEMPLATE_FILE), err)
	}

	tmpl := template.Must(template.New("runtime").Funcs(funcMap).Parse(string(template_doc)))

	var buff bytes.Buffer
	if err := tmpl.Execute(&buff, tmpl_data); err != nil {
		log.Fatal(err, "Failed to apply the template")
	}


	fmt.Println(string(buff.Bytes()))

}
