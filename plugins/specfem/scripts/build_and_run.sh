MPIRUN_CMD="mpirun --bind-to none --report-child-jobs-separately --allow-run-as-root --mca btl ^openib -mca pml ob1 --mca btl_tcp_if_include enp1s0f1 -np $SPECFEM_MPI_NPROC --hostfile $BUILD_DIR/hostfile.mpi"

if [ "$SPECFEM_USE_PODMAN" == "1" ]; then
  MPIRUN_CMD="$MPIRUN_CMD \
        --mca orte_tmpdir_base /tmp/podman-mpirun \
        --mca btl_base_warn_component_unused 0 \
        --mca btl_vader_single_copy_mechanism none \
    podman run --rm --env-host \
     -v /tmp/podman-mpirun:/tmp/podman-mpirun \
     -v $SHARED_SPECFEM:$SHARED_SPECFEM \
     --userns=keep-id --net=host --pid=host --ipc=host \
     --workdir=$SHARED_SPECFEM \
     $PODMAN_BASE_IMAGE"
   echo "$(date) Using PODMAN platform"
else 
   echo "$(date) Using BAREMETAL platform"
fi

mkdir -p "$SHARED_SPECFEM/bin"
cp "$BUILD_DIR"/run_{mesher,solver}.sh "$SHARED_SPECFEM"
cp "$BUILD_DIR/DATA" "$SHARED_SPECFEM" -r

rm -f {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xspecfem3D {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xmeshfem3D

echo "$(date) Building the mesher ..."
cd "$BUILD_DIR"
make clean >/dev/null 2>/dev/null
if ! make mesh -j32 >/dev/null 2>/dev/null; then
  make mesh -j8
  echo Mesher build failed ...
  exit 1
fi
echo "$(date) Mesher built."

cp {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xmeshfem3D

rm -rf "$SHARED_SPECFEM"/{DATABASES_MPI,OUTPUT_FILES}/
mkdir -p "$SHARED_SPECFEM"/{DATABASES_MPI,OUTPUT_FILES}/

cd "$SHARED_SPECFEM"

echo "$(date) Running the mesher ... $SPECFEM_CONFIG"
$MPIRUN_CMD  bash ./run_mesher.sh |& grep -v "Warning: Permanently added"
echo "$(date) Mesher execution done."

cp {"$SHARED_SPECFEM","$BUILD_DIR"}/OUTPUT_FILES/values_from_mesher.h 

cd "$BUILD_DIR"

echo "$(date) Building the solver ..."
if ! make spec -j32 >/dev/null 2>/dev/null; then
  make spec -j8
  echo $(date) Solver build failed ...
  exit 1
fi
echo "$(date) Solver built."

cp {"$BUILD_DIR","$SHARED_SPECFEM"}/bin/xspecfem3D
sync

cd "$SHARED_SPECFEM"
echo "$(date) Running the solver ... $SPECFEM_CONFIG"
$MPIRUN_CMD bash ./run_solver.sh |& grep -v "Warning: Permanently added"
echo "$(date) Solver execution done."

cp {"$SHARED_SPECFEM","$BUILD_DIR"}/OUTPUT_FILES/output_solver.txt
