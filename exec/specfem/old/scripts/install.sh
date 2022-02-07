#! /bin/bash

# must match plugins.specfem.measurement.specfem_baremetal.CONFIGURE_SH:
DATA_DIR="/data/kpouget"
BUILD_DIR="$DATA_DIR/specfem3d_globe"
SHARED_DIR="/mnt/cephfs/kevin"
SHARED_SPECFEM="$SHARED_DIR/specfem"
###

dnf -y install sudo pkg-config gcc-gfortran gcc-c++ openmpi-devel openmpi
dnf -y cuda

mkdir "$SHARED_SPECFEM"/{bin,DATABASES_MPI,OUTPUT_FILES} -p

cd "$DATA_DIR"

git clone https://gitlab.com/kpouget_psap/specfem3d_globe.git --depth 1

cp {"$BUILD_DIR","$SHARED_SPECFEM"}/DATA -r

cd "$BUILD_DIR"

 ./configure --enable-openmp FLAGS_CHECK=-Wno-error \
             --with-cuda CUDA_LIB=/usr/local/cuda-11.0/targets/x86_64-linux/lib/ PATH="$PATH:/usr/lib64/openmpi/bin/"
