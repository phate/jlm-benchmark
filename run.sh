#!/usr/bin/env bash
set -eu

# This script is used for unpacking benchmarks and compiling benchmarks using jlm-opt.

# Check if llvm-config of correct version exists in the PATH
# and if found set the LLVM_BIN to llvm's bindir
LLVM_VERSION=18
LLVM_CONFIG_BIN=llvm-config-${LLVM_VERSION}
if command -v ${LLVM_CONFIG_BIN} &> /dev/null
then
	LLVM_BIN=$(${LLVM_CONFIG_BIN} --bindir)
else
	LLVM_BIN=""
fi

# Check if we can find jlm-opt
if command -v ../../build/jlm-opt &> /dev/null
then
	JLM_OPT="--jlm-opt ../../build/jlm-opt"
else
	JLM_OPT=""
fi

# Used for executing only specific benchmarks
EXTRA_BENCH_OPTIONS=""

# Used to determine which benchmarks to extract
FILTER_BENCHMARK=""
EXTRACT_ALL=true
EXTRACT_SPEC=false
EXTRACT_EMACS=false
EXTRACT_GHOSTSCRIPT=false
EXTRACT_GDB=false
EXTRACT_SENDMAIL=false
FULL_SPEC=false

# Sources to be compiled
SOURCES_JSON="sources/sources-redist2017.json"

# Parameters for deciding what the scripts should perform
BUILD_JLM=false
DRY_RUN=false
CREATE_JSON=false

# Execute benchmarks in parallel by default
if [[ "$OSTYPE" == "darwin"* ]]; then
  PARALLEL_INVOCATIONS=`sysctl -n hw.ncpu`
else
  PARALLEL_INVOCATIONS=`nproc`
fi

function usage()
{
	echo "Usage: ./run-ci.sh [OPTION]"
	echo ""
	echo "  --parallel #THREADS   The number of threads to run in parallel."
	echo "                        Default=[${PARALLEL_INVOCATIONS}]"
	echo "  --jlm-opt             Path to the jlm-opt binary."
	echo "                        Default=[${JLM_OPT}]"
	echo "  --llvm-bin            Path to the llvm binary directory."
	echo "                        Default=[${LLVM_BIN}]"
	echo "  --build-jlm           Clone the jlm repository and build debug and release."
	echo "  --full-spec           Use the full version of SPEC."
	echo "  --dry-run             Do all setup except actually compiling benchmarks."
	echo "  --create-json         Build selected benchmarks to re-create sources.json."
	echo "  --polybench           Compile polybench."
	echo "  --spec                Extract and compile SPEC."
	echo "  --emacs               Extract and compile emacs."
	echo "  --ghostscript         Extract and compile ghostscript."
	echo "  --gdb                 Extract and compile gdb."
	echo "  --sendmail            Extract and compile sendmail."
	echo "  --clean               Delete extracted sources and build files including jlm."
	echo "  --help                Prints this message and stops."
}

while [[ "$#" -ge 1 ]] ; do
	case "$1" in
		--clean)
			echo "Deleting jlm-opt builds"
			just clean-jlm-builds
			echo "Deleting extracted sources"
			just sources/programs/clean-all
			echo "Removing all result files from previous runs of jlm-opt"
			just purge
			exit 1
			;;
		--parallel)
			shift
			PARALLEL_INVOCATIONS=$1
			shift
			;;
		--jlm-opt)
			shift
			JLM_OPT="--jlm-opt $(readlink -m "$1")"
			shift
			;;
		--llvm-bin)
			shift
			LLVM_BIN=$(readlink -m "$1")
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
		--create-json)
			CREATE_JSON=true
			shift
			;;
		--polybench)
			FILTER_BENCHMARK="--filter=polybench"
			EXTRACT_ALL=false
			shift
			;;
		--spec)
			FILTER_BENCHMARK="--filter=500\\.perlbench|502\\.gcc|507\\.cactuBSSN|525\\.x264|526\\.blender|538\\.imagick|544\\.nab|557\\.xz"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--perlbench)
			FILTER_BENCHMARK="--filter=500\\.perlbench"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--gcc)
			FILTER_BENCHMARK="--filter=502\\.gcc"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--cactuBSSN)
			FILTER_BENCHMARK="--filter=507\\.cactuBSSN"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--x264)
			FILTER_BENCHMARK="--filter=525\\.x264"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--blender)
			FILTER_BENCHMARK="--filter=526\\.blender"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--imagick)
			FILTER_BENCHMARK="--filter=538\\.imagick"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--nab)
			FILTER_BENCHMARK="--filter=544\\.nab"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--xz)
			FILTER_BENCHMARK="--filter=557\\.xz"
			EXTRACT_SPEC=true
			EXTRACT_ALL=false
			shift
			;;
		--emacs)
			FILTER_BENCHMARK="--filter=emacs"
			EXTRACT_EMACS=true
			EXTRACT_ALL=false
			shift
			;;
		--ghostscript)
			FILTER_BENCHMARK="--filter=ghostscript"
			EXTRACT_GHOSTSCRIPT=true
			EXTRACT_ALL=false
			shift
			;;
		--gdb)
			FILTER_BENCHMARK="--filter=gdb"
			EXTRACT_GDB=true
			EXTRACT_ALL=false
			shift
			;;
		--sendmail)
			FILTER_BENCHMARK="--filter=sendmail"
			EXTRACT_SENDMAIL=true
			EXTRACT_ALL=false
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
if [ ${EXTRACT_ALL} = true ] || [ ${EXTRACT_SPEC} = true ]; then
	echo "Extracting SPEC ."
	if [ ${FULL_SPEC} = true ]; then
		if [ ! -f programs/cpu2017.tar.xz ]; then
			echo "Not able to find 'programs/cpu2017.tar.xz'".
			exit 1
		fi
		just programs/extract-cpu2017
		SOURCES_JSON="sources/sources.json"
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

# Instead of benchmarking jlm-opt, the user has requested to build all benchmarks to re-create sources.json
if [[ ${CREATE_JSON} = true ]]; then
    echo "Performing full builds of all benchmarks, and tracing compilation commands"
    just build-all-benchmarks

    echo " - Creating sources.json and sources-redist2017.json"
    just create-sources-json

    exit 0
fi
popd

# Build the jlm-opt binary
if [[ ${BUILD_JLM} = true ]]; then
	echo "Building jlm-opt"
	just clone-jlm
	just build-release
	just build-debug
fi

# Ensure Ctrl-C quits immediately, without starting the next command
function sigint() {
    echo "${0}: Aborted by user action (SIGINT)"
    exit 1
}
trap sigint SIGINT

echo "Starting benchmarking of jlm-opt"
set +e

if [ ${DRY_RUN} = true ]; then
	EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} --dry-run"
fi

EXTRA_BENCH_OPTIONS="${EXTRA_BENCH_OPTIONS:-} ${FILTER_BENCHMARK}"

mkdir -p build statistics
echo "./benchmark.py ${JLM_OPT} --llvmbin ${LLVM_BIN} --sources=${SOURCES_JSON} -j${PARALLEL_INVOCATIONS} ${EXTRA_BENCH_OPTIONS:-} --regionAwareModRef --builddir build/ci --statsdir statistics/ci"
./benchmark.py ${JLM_OPT} --llvmbin ${LLVM_BIN} --sources=${SOURCES_JSON} -j${PARALLEL_INVOCATIONS} ${EXTRA_BENCH_OPTIONS:-} --regionAwareModRef --builddir build/ci --statsdir statistics/ci

exit 0
