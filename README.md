# jlm benchmarking repository

## Initial setup
Make sure all the dependencies listed in `apt-install-dependencies.sh` are installed.

The script `run.sh` invokes the necessary commands for extracing benchmarks and compiling them.
It can also clone and build jlm, if requested.

By default, the script will use the included `redist2017` folder for SPEC2017.
It contains redistributable sources for most of the C benchmarks, but does not contain the `505.mcf` benchmark,
and uses a subset of the sources on `500.perlbench`.
All the other benchmarks should give the same results. See `sources/README.md` for details.

If you have a copy of SPEC2017, you can place it inside the `sources/programs/` folder.
It should be a file called `cpu2017.tar.xz` containing files like `install.sh`.
With it in place, you can pass `--full-spec` to the `./run.sh` script.

To check if the programs were compiled correctly, you can pass `--do-validation` to run some simple checks.

## Configuring the benchmarking

### Path to jlm
By default the `run.sh` script assumes that `jlm-opt` is located at `jlm/build-release/jlm-opt`.
A different path can be specified using `--jlm-opt <path>`.
This will also update the location where `jlm` is cloned and built, if using `--build-jlm`.

You can change the default location of `jlm` by creating an `.env` file containing:
```
JLM_PATH=../jlm
```
Note that `jlm` should be in a subdirectory of the benchmarking repository if using docker, or be manually mounted into the container.

### Extra options to `benchmark.py`
Inside `run.sh` you can modify the variable `EXTRA_BENCH_OPTIONS` to pass arguments to the `benchmark.py` script.
Here you can specify things like filters on which benchmarks to include, or timeouts for `jlm-opt` invocations.

When running your own experiments, you should add new command line arguments inside `benchmark.py`,
and then trigger them from `run.sh`, either using `EXTRA_BENCH_OPTIONS`, or by manually changing the invocations at the bottom of the file.

## Running with Docker
The easiest way to run the benchmarks is using the provided `Dockerfile`.

Build a docker image with all the needed dependencies using
``` sh
docker build -t jlm-benchmark-image .
```

Before running benchmarks, configure your CPU to run at a stable frequency where it does not boost or throttle, e.g., using
``` sh
sudo cpupower frequency-set --min 3GHz --max 3GHz --governor performance
```

Then mount the current directory and run the script `./run.sh` inside a Docker container using
``` sh
docker run -it --mount type=bind,source="$(pwd)",target=/benchmark jlm-benchmark-image ./run.sh --build-jlm
```

The resulting container does the following:
   
 - Extracts the benchmark programs. The tarballs in `sources/programs/` are extracted in place.
   Some of the benchmarks are also configured and built, because the build process creates some header files that are necessary for compiling.
   
 - Clones the jlm compiler (if not already cloned)
   
 - Builds the jlm compiler
   
 - Runs the benchmarking

## Restarting benchmarking
If the `run.sh` script is for some reason aborted, it can be restarted and resume roughly where it left off.

If you wish to reset all progress made by the script and start from scratch, you can pass `--clean` to the run script like so:
``` sh
docker run -it --mount type=bind,source="$(pwd)",target=/benchmark jlm-benchmark-image ./run.sh --clean
```
This will remove all extracted benchmarks, and any results from previous runs.

## Running without docker
If you install all dependencies mentioned in the `Dockerfile`, you can run without docker.
However, some dependencies may be located in different locations on your system.
This will affect the compilation commands, so the file `sources/sources.json` will need to be re-made.
See sources/README.md for details.

If you prefer Apptainer over docker, there is an Apptainer definition file in the `extras/` folder that is equivalent to the `Dockerfile`.
It can be used without re-creating `sources.json`.

### Running across SLURM nodes (a bit outdated)
The SLURM setup uses Apptainer, so build the image first, using the apptainer definition file in the `extras/` folder.
``` sh
apptainer build --fakeroot jlm-benchmark.sif extras/jlm-benchmark.def
```

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

