if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  set -x

  echo "$(date) Preparing the working directory to run the solver..." >&2
fi

if [ "$SPECFEM_USE_SHARED_FS" == true ]; then
  WORK_DIR=/$SHARED_SPECFEM-$OMPI_COMM_WORLD_RANK
else
  WORK_DIR=$DATA_DIR/specfem/$OMPI_COMM_WORLD_RANK
fi

mkdir -p "$WORK_DIR"
cp $SHARED_SPECFEM/* "$WORK_DIR/" -r

NEX_VALUE=$(cat $WORK_DIR/DATA/Par_file | grep NEX_XI | awk '{ print $3}')

export OMP_NUM_THREADS

cd "$WORK_DIR"
echo "Running with $OMP_NUM_THREADS threads on rank #$OMPI_COMM_WORLD_RANK problem size $NEX_VALUE from $PWD on $(hostname)"
./bin/xspecfem3D "$@"

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo $(date) Solver done. >&2

  cp OUTPUT_FILES/output_solver.txt "$SHARED_SPECFEM/OUTPUT_FILES/"
fi

if [ "$SPECFEM_USE_SHARED_FS" != true ]; then
  rm -rf "$WORK_DIR"
fi

echo Solver done $OMPI_COMM_WORLD_RANK
