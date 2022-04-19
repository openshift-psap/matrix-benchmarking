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
	Machine string
}

type TemplateBase struct {
	Manifests *map[string]string
}

var flag_name = flag.String("name", "", "")

var flag_np = flag.String("np", "", "")
var flag_machine = flag.String("machine", "", "")

var OSU_MPI_PATH = "/opt/osu-micro-benchmarks/libexec/osu-micro-benchmarks/mpi/"

func main() {
	flag.Parse()

	var cmd, name, image string
	var nproc int
	if *flag_name == "" {
		log.Fatal("Please pass a -name value")
	}

	if *flag_machine == "" {
		log.Fatal("Please pass a -machine value")
	}

	if *flag_name == "latency" || *flag_name == "bandwidth" {
		var bin string
		if *flag_name == "bandwidth" {
			bin = "pt2pt/osu_bw"
		} else {
			bin = "pt2pt/osu_latency"
		}
		cmd = OSU_MPI_PATH + bin

		name = *flag_name + "-2procs"

		nproc = 2

		image = "image-registry.openshift-image-registry.svc:5000/mpi-benchmark/mpi-bench:osu-bench"

	} else if *flag_name == "osu-allreduce" || *flag_name == "osu-alltoall" {
		var bin string

		name = strings.Replace(*flag_name, "_", "-", -1) + "-" + *flag_np + "procs"

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

		image = "image-registry.openshift-image-registry.svc:5000/mpi-benchmark/mpi-bench:osu-bench"
	} else if *flag_name == "hello" {
		name = "hello" + "-" + *flag_np + "procs"

		cmd = "echo hello world"

		if *flag_np == "" {
			log.Fatal("Please pass -np flag")
		}

		var err error
		nproc, err = strconv.Atoi(*flag_np)
		if err != nil {
			log.Fatalf("Failed to parse '-np %s'", *flag_np, err)
		}

		image = "image-registry.openshift-image-registry.svc:5000/mpi-benchmark/mpi-bench:osu-bench"

	} else {
		log.Fatalf("Invalid -name value: '%s'", *flag_name)
	}

	if name == "" {
		log.Fatal("Name cannot be empty ...")
	}

	tmpl_data := MpiBenchmarkData{
		Bench: *flag_name,
		Name: name,
		Image: image,
		Nproc: nproc,
		Command: cmd,
		Machine: *flag_machine,
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
