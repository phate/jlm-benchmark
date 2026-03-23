# Extras folder

This folders contains parts of the original benchmarking setup.
It contains:
 - `jlm-benchmark.sif` the Apptainer Image description file used to run benchmarks
 - A bunch of SLURM scripts for running jobs, and extra scripts for re-running ones that timed out.

## Building apptainer image
The image must be built from the root of the repository:
``` sh
apptainer build --fakeroot jlm-benchmark.sif extras/jlm-benchmark.def
```

## Running with SLURM
Before benchmarking, make sure you delete any old statistics and logs.
```sh
apptainer exec jlm-benchmark.sif just purge
rm -rf slurm-log
```

Then make sure sources are extracted and `jlm-opt` is built using:
``` sh
apptainer exec jlm-benchmark.sif ./run.sh dry-run
```

Then run `extras/run-slurm.sh` like so:
```sh
mkdir -p statistics build
APPTAINER_CONTAINER=jlm-benchmark.sif sbatch extras/run-slurm.sh
```
