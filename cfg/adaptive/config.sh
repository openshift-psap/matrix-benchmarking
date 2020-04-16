#! /bin/bash

_THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

LOCAL_BASE_DIR="$(realpath $_THIS_DIR/../../)"
SERVER_BASE_DIR=$LOCAL_BASE_DIR
VM_BASE_DIR=$LOCAL_BASE_DIR

YAML_FILE="$LOCAL_BASE_DIR/cfg/adaptive/agents.yaml"

cfg_get() {
    cat $YAML_FILE | yq .$1 -r
}

machines=$(cfg_get setup.machines)

if [[ "$machines" == "desktop" ]]; then
    VM_SCREEN_NAME="DP-2"
fi

SERVER=$(cfg_get machines.$machines.server)
VM=$(cfg_get machines.$machines.vm)

VM_SPICE_STREAMING_AGENT="$HOME/spice/spice-streaming-agent/build/src/spice-streaming-agent"
VM_SPICE_STREAMING_PLUGINS_DIR="$(dirname $VM_SPICE_STREAMING_AGENT)"
SPICE_STREAMING_ENV="SPICE_AGENT_INTERFACE_GUEST_PORT=1236 \
LIBVA_DRIVER_NAME=i965"

# format: "CODEC GST_ENCODER[:CODEC GST_ENCODER]*"
# see `gst-inspect-1.0 | grep enc` for the list of gst encoders
SPICE_ENCODING_OPT="-c framerate=30"
SPICE_STREAMING_GST_PLUGINS="vp8 vaapivp8enc:vp8 vp8enc"

VM_DISPLAY_DESK_IMG=$HOME/desk/lady-musgrave-blue.png
VM_DISPLAY_VIDEO_PATH=$HOME/desk

HOST_INTEL_GPU_FREQ_DIR="/sys/bus/pci/devices/0000:00:02.0/drm/card0"
HOST_INTEL_GPU_DEFAULT_PERF_ON=1200
HOST_INTEL_GPU_DEFAULT_PERF_OFF=350
HOST_CPU_GOV_FILES="/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
