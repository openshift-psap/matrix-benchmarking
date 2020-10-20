if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo "$(date) Preparing the working directory to run the mesher ..." >&2
  set -x
fi

SPECFEM_SHARED_CACHE=${SHARED_SPECFEM}/cache/${SPECFEM_MPI_NPROC}proc/${SPECFEM_NEX}nex

if [ "$SPECFEM_USE_SHARED_FS" == true ]; then
  WORK_DIR=$SPECFEM_SHARED_CACHE
else
  WORK_DIR=$DATA_DIR/specfem/$OMPI_COMM_WORLD_RANK
  rm -rf "$WORK_DIR/"
  mkdir -p "$WORK_DIR/"

  cp "$SPECFEM_SHARED_CACHE" "$WORK_DIR/" -rf
fi

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  NEX_VALUE=$(cat $WORK_DIR/DATA/Par_file | grep NEX_XI | awk '{ print $3}')

  echo $(date) Running the mesher >&2
fi


export OMP_NUM_THREADS

cd "$WORK_DIR/"
echo "$(date) Running the mesher with $OMP_NUM_THREADS threads on rank #$OMPI_COMM_WORLD_RANK/$OMPI_COMM_WORLD_SIZE nex=$NEX_VALUE from $PWD"
./bin/xmeshfem3D

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo "$(date) Mesher done" >&2

  if [ "$SPECFEM_USE_SHARED_FS" != true ]; then
      cp "$WORK_DIR/OUTPUT_FILES/" "$SPECFEM_SHARED_CACHE/" -r
  fi
fi
if [ "$SPECFEM_USE_SHARED_FS" != true ]; then
    cp -f DATABASES_MPI/* "$SPECFEM_SHARED_CACHE/DATABASES_MPI/"

    rm -rf "$WORK_DIR"
fi

echo "$(date) Mesher done $OMPI_COMM_WORLD_RANK"
