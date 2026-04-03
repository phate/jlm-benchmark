#!/usr/bin/env bash
set -eu

# This script is used for unpacking benchmarks and compiling benchmarks using jlm-opt.

# source .env if it exists
if [ -f .env ]; then
	source .env
fi

# Assign defaults if not already specified as environment variables.
# These can also be overwritten using --options
LLVM_CONFIG="${LLVM_CONFIG:-llvm-config-18}"
JLM_OPT="${JLM_OPT:-${JLM_PATH:-jlm}/build-release/jlm-opt}"

# Execute benchmarks in parallel by default
if [[ "$OSTYPE" == "darwin"* ]]; then
  PARALLEL_INVOCATIONS=`sysctl -n hw.ncpu`
else
  PARALLEL_INVOCATIONS=`nproc`
fi

# Options added to the final ./benchmark.py invocation
EXTRA_BENCH_OPTIONS=""

# Used to determine which benchmarks to extract
EXTRACT_ALL=true
EXTRACT_SPEC=false
EXTRACT_EMACS=false
EXTRACT_GHOSTSCRIPT=false
EXTRACT_GDB=false
EXTRACT_SENDMAIL=false
EXTRACT_EMBENCH=false

# If true, a real copy of cpu2017 is used, instead of the included redist2017
FULL_SPEC=false
# Path to sources json file containing benchmark compilation descriptions
SOURCES_JSON="sources/sources.json"

# Parameters for deciding what tasks the script should perform
BUILD_JLM=false
DRY_RUN=false
CREATE_JSON=false

function usage()
{
	echo "Usage: ./run.sh [OPTION]"
	echo ""
	echo "  --parallel <threads>  The number of threads to run in parallel."
	echo "                        Default=[${PARALLEL_INVOCATIONS}]"
	echo "  --jlm-opt <path>      Specify the path to jlm-opt."
	echo "                        Default=[${JLM_OPT}]"
	echo "  --llvm-config <path>  Path to the llvm config binary."
	echo "                        Default=[${LLVM_CONFIG}]"
	echo "  --build-jlm           Clone the jlm repository and build debug and release."
	echo "                        Uses the given jlm-opt path to decide directory."
	echo "  --full-spec           Use the full version of SPEC instead of redist2017. Requires cpu2017.tar.xz."
	echo "  --dry-run             Do all setup except actually compiling benchmarks."
	echo "  --do-validation       Execute validation scripts after compiling benchmarks."
	echo ""
	echo "  Optional filters:     (or none to select all)"
	echo "    --spec              Compile SPEC (redist or full)."
	echo "    --emacs             Compile emacs."
	echo "    --ghostscript       Compile ghostscript."
	echo "    --gdb               Compile gdb."
	echo "    --sendmail          Compile sendmail."
	echo "    --polybench         Compile Polybench."
	echo "    --embench           Compile Embench IoT."
	echo ""
	echo "  --create-json         Build all benchmarks to re-create sources.json. Implies --full-spec"
	echo "  --clean               Delete extracted sources and build files."
	echo "  --help                Prints this message and stops."
}

while [[ "$#" -ge 1 ]] ; do
	case "$1" in
		--parallel)
			shift
			PARALLEL_INVOCATIONS="$1"
			shift
			;;
		--jlm-opt)
			shift
			JLM_OPT="$(readlink -m "$1")"
			shift
			;;
		--llvm-config)
			shift
			LLVM_CONFIG="$1"
			shift
			;;
		--build-jlm)
			BUILD_JLM=true
			shift
			;;
		--full-spec)
			FULL_SPEC=true
			shift
			;;
		--dry-run)
			DRY_RUN=true
			shift
			;;
		--do-validation)
		    EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --do-validation"
			shift
			;;
		--spec)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=500\\.perlbench|502\\.gcc|507\\.cactuBSSN|525\\.x264|526\\.blender|538\\.imagick|544\\.nab|557\\.xz"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--perlbench)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=500\\.perlbench"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--gcc)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=502\\.gcc"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--cactuBSSN)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=507\\.cactuBSSN"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--x264)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=525\\.x264"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--blender)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=526\\.blender"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--imagick)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=538\\.imagick"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--nab)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=544\\.nab"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--xz)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=557\\.xz"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--emacs)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=emacs"
			EXTRACT_EMACS=true
			EXTRACT_ALL=false
			shift
			;;
		--ghostscript)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=ghostscript"
			EXTRACT_GHOSTSCRIPT=true
			EXTRACT_ALL=false
			shift
			;;
		--gdb)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=gdb"
			EXTRACT_GDB=true
			EXTRACT_ALL=false
			shift
			;;
		--sendmail)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=sendmail"
			EXTRACT_SENDMAIL=true
			EXTRACT_ALL=false
			shift
			;;
		--polybench)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=polybench"
			EXTRACT_ALL=false
			shift
			;;
		--embench)
			EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --filter=embench"
			EXTRACT_EMBENCH=true
			EXTRACT_ALL=false
			shift
			;;
		--clean)
			echo "Deleting extracted sources"
			just sources/programs/clean-all
			echo "Removing all result files from previous runs of jlm-opt"
			just purge
			exit 0
			;;
		--create-json)
			FULL_SPEC=true
			CREATE_JSON=true
			shift
			;;
		--help|*)
			usage >&2
			exit 1
			;;
	esac
done

# Prepare the benchmarks
pushd sources

# If we have requested full spec
if [[ ${FULL_SPEC} = true ]]; then
   # Check that the tarball is in place
   if [ ! -f programs/cpu2017.tar.xz ]; then
	   echo "error: missing file 'sources/programs/cpu2017.tar.xz'".
	   exit 1
   fi
   EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --full-spec"
fi

# Instead of benchmarking jlm-opt, the user has requested to build all benchmarks to re-create sources.json
if [[ ${CREATE_JSON} = true ]]; then
    echo "Performing full builds of all benchmarks, and tracing compilation commands"
    just build-all-benchmarks

    echo " - Creating sources.json"
    just create-sources-json

    exit 0
fi

if [ ${EXTRACT_ALL} = true ] || [ ${EXTRACT_SPEC} = true ]; then
	echo "Extracting SPEC ."
	if [ ${FULL_SPEC} = true ]; then
		just programs/extract-cpu2017
	else
		just programs/extract-redist2017
	fi
fi

if [ ${EXTRACT_ALL} = true ] || [ ${EXTRACT_EMACS} = true ]; then
	echo "Extracting Emacs sources."
	just programs/extract-emacs
fi

if [ ${EXTRACT_ALL} = true ] || [ ${EXTRACT_GHOSTSCRIPT} = true ]; then
	echo "Extracting ghostscript sources."
	just programs/extract-ghostscript
fi

if [ ${EXTRACT_ALL} = true ] || [ ${EXTRACT_GDB} = true ]; then
	echo "Extracting gbd sources."
	just programs/extract-gdb
fi

if [ ${EXTRACT_ALL} = true ] || [ ${EXTRACT_SENDMAIL} = true ]; then
	echo "Extracting gbd sources."
	just programs/extract-sendmail
fi

if [ ${EXTRACT_ALL} = true ] || [ ${EXTRACT_EMBENCH} = true ]; then
	echo "Extracting embench sources."
	just programs/extract-embench
fi
popd

# Build the jlm-opt binary if requested
if [[ ${BUILD_JLM} = true ]]; then

	if [[ "${JLM_OPT}" = */build*/jlm-opt ]]; then
	    # Remove the build-*/jlm-opt part of the jlm-opt path to find the jlm path
	    export JLM_PATH="${JLM_OPT%/build*/jlm-opt}"
	else
		echo "Unable to extract a jlm path from the jlm-opt path (${JLM_OPT}). Aborting."
		exit 1
	fi

	echo "Cloning and building jlm in location: ${JLM_PATH}"
	just clone-jlm
	just build-release
	just build-debug
fi

# Extract the LLVM bindir
LLVM_BIN="$(${LLVM_CONFIG} --bindir || true)"
if [[ -z "${LLVM_BIN}" ]]; then
	echo "Unable to extract --bindir from ${LLVM_CONFIG}"
	exit 1
fi

if [ ${DRY_RUN} = true ]; then
	EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --dry-run"
fi

# Ensure Ctrl-C quits immediately, without starting the next command
function sigint() {
    echo "${0}: Aborted by user action (SIGINT)"
    exit 1
}
trap sigint SIGINT

echo "Starting benchmarking of jlm-opt"
mkdir -p build statistics

# Enable echoing commands to print the final benchmark.py invocation
set -x
./benchmark.py --jlm-opt="${JLM_OPT}" --llvmbin="${LLVM_BIN}" --sources="${SOURCES_JSON}" -j="${PARALLEL_INVOCATIONS}" ${EXTRA_BENCH_OPTIONS:-} --regionAwareModRef --builddir build/ci --statsdir statistics/ci

#./benchmark.py --jlm-opt="${JLM_PATH}/build-release/jlm-opt" --llvmbin="${LLVM_BIN}" \
#	--sources="${SOURCES_JSON}" -j="${PARALLEL_INVOCATIONS}" ${EXTRA_BENCH_OPTIONS:-} \
#	--regionAwareModRef --builddir build/raware --statsdir statistics/raware \
#	|| true

#./benchmark.py --jlm-opt="${JLM_PATH}/build-release/jlm-opt" --llvmbin="${LLVM_BIN}" \
#	--sources="${SOURCES_JSON}" -j="${PARALLEL_INVOCATIONS}" ${EXTRA_BENCH_OPTIONS:-} \
#	--regionAwareModRef --useMem2reg --builddir build/raware --statsdir statistics/m2r
