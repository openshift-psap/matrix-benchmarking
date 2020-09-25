if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  set -x
  echo $(date) Preparing the working directory to run the mesher ... >&2
fi

if [ "$SPECFEM_USE_SHARED_FS" == true ]; then
  WORK_DIR=/$SHARED_SPECFEM-$OMPI_COMM_WORLD_RANK
else
  WORK_DIR=$DATA_DIR/specfem/$OMPI_COMM_WORLD_RANK
fi

rm -rf "$WORK_DIR/"
mkdir -p "$WORK_DIR/"

cp ./ "$WORK_DIR/" -rf

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo Running the mesher from "$WORK_DIR" ...
  echo $(date) Running the mesher >&2
fi

export OMP_NUM_THREADS

cd "$WORK_DIR/"
./bin/xmeshfem3D "$@"

if [[ -z "$OMPI_COMM_WORLD_RANK" || "$OMPI_COMM_WORLD_RANK" -eq 0 ]]; then
  echo $(date) Mesher done >&2
  rm -rf "$SHARED_SPECFEM/OUTPUT_FILES/"
  cp OUTPUT_FILES/ "$SHARED_SPECFEM/" -r
fi

cp -f DATABASES_MPI/* "$SHARED_SPECFEM/DATABASES_MPI/"

if [ "$SPECFEM_USE_SHARED_FS" != true ]; then
  rm -rf "$WORK_DIR"
fi

echo Mesher done $OMPI_COMM_WORLD_RANK
