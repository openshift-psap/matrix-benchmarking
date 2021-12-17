if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo "$(date) Preparing the working directory to run the new solver ..." >&2
  set -x
fi

SPECFEM_SHARED_CACHE=${SHARED_SPECFEM}/cache/${SPECFEM_MPI_NPROC}proc/${SPECFEM_NEX}nex

if [ "$SPECFEM_USE_SHARED_FS" == true ]; then
  WORK_DIR=$SPECFEM_SHARED_CACHE
else
  WORK_DIR=$DATA_DIR/specfem/$OMPI_COMM_WORLD_RANK
  mkdir -p "$WORK_DIR"
  cp $SPECFEM_SHARED_CACHE/* "$WORK_DIR/" -r
fi

export OMP_NUM_THREADS

cd "$WORK_DIR"

NEX_VALUE=$(cat $WORK_DIR/DATA/Par_file | grep NEX_XI | awk '{ print $3}')

echo "$(date) Running the solver with $OMP_NUM_THREADS threads on rank #$OMPI_COMM_WORLD_RANK/$OMPI_COMM_WORLD_SIZE nex=$NEX_VALUE from $PWD"
./bin/xspecfem3D

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo $(date) Solver done. >&2

  if [ "$SPECFEM_USE_SHARED_FS" != true ]; then
      cp OUTPUT_FILES/output_solver.txt "$SPECFEM_SHARED_CACHE/OUTPUT_FILES/"
  fi
fi

if [ "$SPECFEM_USE_SHARED_FS" != true ]; then
  rm -rf "$WORK_DIR"
fi

echo "Solver done $OMPI_COMM_WORLD_RANK"
