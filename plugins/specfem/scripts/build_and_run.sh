set -e

MPIRUN_CMD="mpirun --bind-to none --report-child-jobs-separately --allow-run-as-root --mca btl ^openib -mca pml ob1 --mca btl_tcp_if_include enp1s0f1 -np $SPECFEM_MPI_NPROC --hostfile $BUILD_DIR/hostfile.mpi"

SPECFEM_SHARED_CACHE=${SHARED_SPECFEM}/cache/${SPECFEM_MPI_NPROC}proc/${SPECFEM_NEX}nex

if [ "$SPECFEM_USE_PODMAN" == "1" ]; then
  MPIRUN_CMD="$MPIRUN_CMD \
        --mca orte_tmpdir_base /tmp/podman-mpirun \
        --mca btl_base_warn_component_unused 0 \
        --mca btl_vader_single_copy_mechanism none \
    podman run --rm --env-host \
     -v /tmp/podman-mpirun:/tmp/podman-mpirun \
     -v $SPECFEM_SHARED_CACHE:$SPECFEM_SHARED_CACHE \
     --userns=keep-id --net=host --pid=host --ipc=host \
     --workdir=$SPECFEM_SHARED_CACHE"

  if [ "$SPECFEM_PLATFORM" == "podman-no-seccomp" ]; then
      MPIRUN_CMD="$MPIRUN_CMD --security-opt seccomp=unconfined"
  fi

  MPIRUN_CMD="$MPIRUN_CMD \
              $PODMAN_BASE_IMAGE"
   echo "$(date) Using PODMAN platform"
else
   echo "$(date) Using BAREMETAL platform"
fi


if [ -e "$SPECFEM_SHARED_CACHE" ]; then
    echo "$(date) Mesh found in cache; reusing it."
    cp "$BUILD_DIR"/run_{mesher,solver}.sh "$SPECFEM_SHARED_CACHE"
else
    mkdir -p "$SPECFEM_SHARED_CACHE/bin"
    cp "$BUILD_DIR"/run_{mesher,solver}.sh "$SPECFEM_SHARED_CACHE"
    cp "$BUILD_DIR/DATA" "$SPECFEM_SHARED_CACHE" -r

    rm -f "$BUILD_DIR/bin/xspecfem3D" "$BUILD_DIR/bin/xmeshfem3D"

    echo "$(date) Building the mesher ..."
    cd "$BUILD_DIR"
    make clean >/dev/null 2>/dev/null
    if ! make mesh -j32 >/dev/null 2>/dev/null; then
        make mesh # rebuild for the logs
        echo "Mesher build failed ..."
        cd /
        rm -rf "$SPECFEM_SHARED_CACHE"
        exit 1
    fi
    echo "$(date) Mesher built."

    cp {"$BUILD_DIR","$SPECFEM_SHARED_CACHE"}/bin/xmeshfem3D

    mkdir -p "$SPECFEM_SHARED_CACHE"/{DATABASES_MPI,OUTPUT_FILES}/

    cd "$SPECFEM_SHARED_CACHE"

    echo "$(date) Running the mesher ..."
    echo "$(date) $SPECFEM_CONFIG"
    $MPIRUN_CMD  bash ./run_mesher.sh || true

    if ! [ -e "$SPECFEM_SHARED_CACHE/OUTPUT_FILES/values_from_mesher.h" ]; then
        echo "ERROR: Specfem finished after mesher execution failed ..."
        cd /
        rm -rf "$SPECFEM_SHARED_CACHE"
        exit 1
    fi

    cp "$SPECFEM_SHARED_CACHE/OUTPUT_FILES/values_from_mesher.h" "$BUILD_DIR/OUTPUT_FILES"
    echo "$(date) Mesher execution done."

    cd "$BUILD_DIR"
    echo "$(date) Building the solver ..."
    if ! make spec -j32 >/dev/null 2>/dev/null; then
        make spec # redo for the logs

        echo "ERROR: Specfem finished after solver build failed ..."
        exit 1
    fi
    echo "$(date) Solver built."

    cp {"$BUILD_DIR","$SPECFEM_SHARED_CACHE"}/bin/xspecfem3D
    sync
fi

cd "$SPECFEM_SHARED_CACHE"
echo "$(date) Running the solver ... $SPECFEM_CONFIG"
$MPIRUN_CMD bash ./run_solver.sh
echo "$(date) Solver execution done."

if ! [ -e "$SPECFEM_SHARED_CACHE/OUTPUT_FILES/output_solver.txt" ]; then
    echo "ERROR: Specfem finished after solver execution failed ..."
    exit 1
fi

cp {"$SPECFEM_SHARED_CACHE","$BUILD_DIR"}/OUTPUT_FILES/output_solver.txt
