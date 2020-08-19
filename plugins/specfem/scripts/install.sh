#! /bin/bash

# must match SpecfemSimpleAgent.CONFIGURE_SH:
DATA_DIR="/data/kevin"
BUILD_DIR="$DATA_DIR/specfem3d_globe"
SHARED_DIR="/mnt/fsx/kevin"
SHARED_SPECFEM="$SHARED_DIR/specfem"
###

CP=/usr/bin/cp

dnf -y install sudo pkg-config gcc-gfortran gcc-c++ openmpi-devel openmpi

mkdir "$SHARED_SPECFEM"/{bin,DATABASES_MPI,OUTPUT_FILES} -p

cd "$DATA_DIR"

git clone https://gitlab.com/kpouget_psap/specfem3d_globe.git --depth 1

$CP {"$BUILD_DIR","$SHARED_SPECFEM"}/DATA -r

cd "$BUILD_DIR"

./configure --enable-openmp FLAGS_CHECK=-Wno-error
