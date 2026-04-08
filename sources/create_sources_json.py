#!/usr/bin/env python3
import argparse
import os
import shlex
import json
import sys
import subprocess
import re

PROGRAM_FOLDER = "programs"
SPEC2017_FOLDER = f"{PROGRAM_FOLDER}/cpu2017/benchspec/CPU"
REDIST2017_FOLDER = f"{PROGRAM_FOLDER}/redist2017/extracted"
POLYBENCH_FOLDER = f"{PROGRAM_FOLDER}/polybench-c-4.2.1-beta"
EMBENCH_FOLDER = f"{PROGRAM_FOLDER}/embench-1.0"

VALIDATOR_FOLDER = "validators"
EMBENCH_VALIDATOR = f"{VALIDATOR_FOLDER}/embench/validate.sh"

# The script should be run from the sources folder
SCRIPT_ROOT = os.getcwd()

# C++ compilers can also be used to compile / link C, so handle them all
C_COMPILERS = ["clang", "clang18", "gcc", "jlc", "cc", "clang++", "clang++18", "g++"]
FORTRAN_COMPILERS = ["gfortran"]
LINKERS = C_COMPILERS
# Some programs create archives before the final linking command
ARCHIVERS = ["ar"]

# Compilation commands for SPEC are extracted from the buildXXX/make.out log file
SPEC2017_PROGRAMS = [
    "cpu2017-500.perlbench",
    "cpu2017-502.gcc",
    "cpu2017-505.mcf",
    "cpu2017-507.cactuBSSN",
    "cpu2017-525.x264",
    "cpu2017-526.blender",
    "cpu2017-538.imagick",
    "cpu2017-557.xz",
    "cpu2017-544.nab"
]

# Redistributable versions of spec benchmarks are created when possible
# They re-use the compilation commands from  the SPEC versions.
# The "dir" field is the replacement path within in the redist2017/extracted/ folder
# For some of the benchmarks, differences between cpu2017 and redist2017 make linking difficult, so we disable it.
REDIST2017_PROGRAMS = {
    # perl in redist fails to compile to LLVM IR
    #"redist2017-500.perlbench": {
    #    "dir": "perl-5.22.1",
    #    "link": False
    #},
    "redist2017-502.gcc": {
        "dir": "502.gcc_r/src",
        "link": True
    },
    "redist2017-507.cactuBSSN": {
        "dir": "507.cactuBSSN_r/src",
        "link": True
    },
    "redist2017-525.x264": {
        "dir": "525.x264_r/src",
        "link": True
    },
    "redist2017-526.blender": {
        "dir": "526.blender_r/src",
        "link": True
    },
    "redist2017-538.imagick": {
        "dir": "ImageMagick-6.8.9-1",
        "link": False
    },
    "redist2017-557.xz": {
        "dir": "557.xz_r/src",
        "link": True
    },
    "redist2017-544.nab": {
        "dir": "544.nab_r/src",
        "link": True
    }
}

# These programs are located directly in the PROGRAM_FOLDER
# Compilation commands to build and link these programs are extracted from events.json
OTHER_PROGRAMS = {
    "emacs-29.4": {
        "elffile": "/src/temacs.tmp$",
        "validator": f"{VALIDATOR_FOLDER}/emacs/validate.sh"
    },
    "ghostscript-10.04.0": {
        "elffile": "/bin/gs"
    },
    "gdb-15.2": {
        "elffile": "/gdb/gdb$"
    },
    "sendmail-8.18.1": {
        "elffile": "/sendmail$",
        "link": False
    }
}

# Compilation commands for Polybench are created manually according to the pattern given in their README
POLYBENCH_PROGRAMS = {
    "polybench-correlation": "datamining/correlation/correlation.c",
    "polybench-covariance": "datamining/covariance/covariance.c",
    "polybench-2mm": "linear-algebra/kernels/2mm/2mm.c",
    "polybench-3mm": "linear-algebra/kernels/3mm/3mm.c",
    "polybench-atax": "linear-algebra/kernels/atax/atax.c",
    "polybench-bicg": "linear-algebra/kernels/bicg/bicg.c",
    "polybench-doitgen": "linear-algebra/kernels/doitgen/doitgen.c",
    "polybench-mvt": "linear-algebra/kernels/mvt/mvt.c",
    "polybench-gemm": "linear-algebra/blas/gemm/gemm.c",
    "polybench-gemver": "linear-algebra/blas/gemver/gemver.c",
    "polybench-gesummv": "linear-algebra/blas/gesummv/gesummv.c",
    "polybench-symm": "linear-algebra/blas/symm/symm.c",
    "polybench-syr2k": "linear-algebra/blas/syr2k/syr2k.c",
    "polybench-syrk": "linear-algebra/blas/syrk/syrk.c",
    "polybench-trmm": "linear-algebra/blas/trmm/trmm.c",
    "polybench-cholesky": "linear-algebra/solvers/cholesky/cholesky.c",
    "polybench-durbin": "linear-algebra/solvers/durbin/durbin.c",
    "polybench-gramschmidt": "linear-algebra/solvers/gramschmidt/gramschmidt.c",
    "polybench-lu": "linear-algebra/solvers/lu/lu.c",
    "polybench-ludcmp": "linear-algebra/solvers/ludcmp/ludcmp.c",
    "polybench-trisolv": "linear-algebra/solvers/trisolv/trisolv.c",
    "polybench-deriche": "medley/deriche/deriche.c",
    "polybench-floyd-warshall": "medley/floyd-warshall/floyd-warshall.c",
    "polybench-nussinov": "medley/nussinov/nussinov.c",
    "polybench-adi": "stencils/adi/adi.c",
    "polybench-fdtd-2d": "stencils/fdtd-2d/fdtd-2d.c",
    "polybench-heat-3d": "stencils/heat-3d/heat-3d.c",
    "polybench-jacobi-1d": "stencils/jacobi-1d/jacobi-1d.c",
    "polybench-jacobi-2d": "stencils/jacobi-2d/jacobi-2d.c",
    "polybench-seidel-2d": "stencils/seidel-2d/seidel-2d.c",
}

# Compilation commands for Embench are created manually
EMBENCH_PROGRAMS = {
    "embench-aha-mont64": ["aha-mont64/mont64.c"],
    "embench-crc32": ["crc32/crc_32.c"],
    "embench-cubic": ["cubic/basicmath_small.c", "cubic/libcubic.c"],
    "embench-edn": ["edn/libedn.c"],
    "embench-huffbench": ["huffbench/libhuffbench.c"],
    "embench-matmult-int": ["matmult-int/matmult-int.c"],
    "embench-minver": ["minver/libminver.c"],
    "embench-nbody": ["nbody/nbody.c"],
    "embench-nettle-aes": ["nettle-aes/nettle-aes.c"],
    "embench-nettle-sha256": ["nettle-sha256/nettle-sha256.c"],
    "embench-nsichneu": ["nsichneu/libnsichneu.c"],
    "embench-picojpeg": ["picojpeg/libpicojpeg.c", "picojpeg/picojpeg_test.c"],
    "embench-qrduino": ["qrduino/qrencode.c", "qrduino/qrframe.c", "qrduino/qrtest.c"],
    "embench-sglib-combined": ["sglib-combined/combined.c"],
    "embench-slre": ["slre/libslre.c"],
    "embench-st": ["st/libst.c"],
    "embench-statemate": ["statemate/libstatemate.c"],
    "embench-ud": ["ud/libud.c"],
    "embench-wikisort": ["wikisort/libwikisort.c"],
}

# All files whose full path end in one of the following should be skipped entirely
DISQUALIFYING_FILES = [
    "conftest.c", # Used by gdb to test the system compiler
    "conftest1.c",
    "conftest2.c",
    "conftest.cpp",
    "Imakefile.c" # Also used by gdb to test the system compiler
]

# Commands with arguments that match any of these regexes should be ignored,
# as they are only used by the build system to extract info
DISQUALIFYING_FLAGS = ["-v", "-V", "--?version", "-qversion", "--?print.*"]

# Object files whose full path end in one of the following are skipped
# when making the final list for the linking command
IGNORED_OFILES = [

    # These files in gdb provide symbols that are already provided by other files
    # This is normally not an issue when the object files are packaged in .a libraries,
    # since the linker skips extracting .o-files that do not provide missing symbols.
    "gdb-15.2/readline/readline/xmalloc.o",
    "gdb-15.2/libiberty/xmalloc.o"
]

# Files whose absolute path end in the following should not pass through jlm-opt,
# due to containing things like inline assembly and special intrinsics we do not currently support,
# They get "kind": "C-nonjlm" in the output json
NONJLM_C_FILES = [
    "emacs-29.4/src/bytecode.c",
    "emacs-29.4/src/json.c",
    "gdb-15.2/libiberty/sha1.c",
    "gdb-15.2/libbacktrace/mmap.c",
    "gdb-15.2/libbacktrace/dwarf.c",
    "gdb-15.2/libbacktrace/elf.c",
    "ghostscript-10.04.0/leptonica/src/bytearray.c",
    "ghostscript-10.04.0/leptonica/src/boxbasic.c",
    "ghostscript-10.04.0/leptonica/src/ccbord.c",
    "ghostscript-10.04.0/leptonica/src/compare.c",
    "ghostscript-10.04.0/leptonica/src/dnabasic.c",
    "ghostscript-10.04.0/leptonica/src/gplot.c",
    "ghostscript-10.04.0/leptonica/src/fpix1.c",
    "ghostscript-10.04.0/leptonica/src/numabasic.c",
    "ghostscript-10.04.0/leptonica/src/pix1.c",
    "ghostscript-10.04.0/leptonica/src/pixabasic.c",
    "ghostscript-10.04.0/leptonica/src/ptabasic.c",
    "ghostscript-10.04.0/leptonica/src/regutils.c",
    "ghostscript-10.04.0/leptonica/src/sarray1.c",
    "ghostscript-10.04.0/leptonica/src/writefile.c",
    "ghostscript-10.04.0/obj/gsromfs1.c",
]

# When these flags appear on their own, the next argument belongs to it, and is not a positional argument
C_FLAGS_WITH_ARGUMENTS = [
    "-I",
    "-include",
    "-D",
    "-o",
    "-x",
    "-MF",
    "-MT",
]
FORTRAN_FLAGS_WITH_ARGUMENTS = C_FLAGS_WITH_ARGUMENTS

# Arguments that should be removed from the C compiler invocation when using jlm
IGNORED_ARGUMENTS = [
    "-O",
    "-O0",
    "-O1",
    "-O2",
    "-O3",
    "-Os",
    "-Oz",
    "-Ofast",
    "-c",
    "-g",
    "-g1",
    "-g2",
    "-g3",
    "-ggdb0",
    "-ggdb1",
    "-ggdb2",
    "-ggdb3",
    "--debug",
    "-gdwarf",
    "-gdwarf-1",
    "-gdwarf-2",
    "-gdwarf-3",
    "-gdwarf-4",
    "-gdwarf-5",
    "-gdwarf32",
    "-gdwarf64",
    "-gfull",
]
C_IGNORED_ARGUMENTS = [*IGNORED_ARGUMENTS, "-std=c++17"]
CXX_IGNORED_ARGUMENTS = [*IGNORED_ARGUMENTS, "-std=c17"]
FORTRAN_IGNORED_ARGUMENTS = C_IGNORED_ARGUMENTS

C_REPLACED_ARGUMENTS = {
    "-fstrict-flex-arrays": "-fstrict-flex-arrays=3"
}

def make_relative_to(path, base):
    """
    Makes a path relative to base. Is must be an absolute path, or relative to the SCRIPT_ROOT.
    Asserts that base is a directory.
    """
    if not path.startswith("/"):
        path = os.path.abspath(path)

    # Remove any .. from the path
    path = os.path.normpath(path)

    base = os.path.abspath(base)
    if not os.path.isdir(base):
        raise ValueError(f"{base} is not a directory")

    prefix = ""
    while True:
        if path.startswith(base + "/"):
            result = prefix + path[len(base)+1:]
            return result
        prefix += "../"
        base = os.path.dirname(base)
        if base == "/": # Workaround for basename of root having trailing /
            base = ""

def ensure_relative_to(path, base):
    return make_relative_to(os.path.join(base, path), base)


def extract(flag, args):
    """
    :param flag: the flag with option to remove, e.g. "-x value"
    :param args: a list on the format [..., "-x", "val", ...]
    :return: a tuple containing ("val", rest_args),
             where rest_args has both "-x" and "val" removed
    """
    assert flag in args
    output_index = args.index(flag)
    value = args[output_index + 1]
    # Remove the flag and value part of args
    return value, args[:output_index] + args[output_index+2:]


class SourceFile:
    """
    Represents the compilation of a single file in a given working directory, with a set of arguments.
    The working dir is stored relative to the script root.
    The srcfile and ofile are stored relative to the working dir.
    """
    def __init__(self, working_dir, srcfile, ofile, kind, arguments):
        """
        :param working_dir: the working directory for the compile command, relative to SCRIPT_ROOT
        :param srcfile: the file to compile, relative to working_dir
        :param ofile: the output object file, relative to working_dir
        :param kind: the kind of file.
        :param arguments: arguments to pass to the compilation command
        """

        # If absolute paths have been provided, make them relative
        self.working_dir = ensure_relative_to(working_dir, SCRIPT_ROOT)
        self.srcfile = ensure_relative_to(srcfile, self.working_dir)
        self.ofile = ensure_relative_to(ofile, self.working_dir)
        self.kind = kind
        self.arguments = [arg for arg in arguments]

        if self.kind not in ["C", "C-nonjlm", "C++", "Fortran"]:
            raise ValueError(f"Unknown SourceFile kind: {kind}")

        full_path = os.path.join(self.working_dir, self.srcfile)
        if not os.path.isfile(full_path):
            raise ValueError(f"source file does not exist: {full_path}")

    def to_dict(self):
        return {
            "working_dir": self.working_dir,
            "srcfile": self.srcfile,
            "ofile": self.ofile,
            "kind": self.kind,
            "arguments": self.arguments
            }

    def copy(self):
        return SourceFile(self.working_dir, self.srcfile, self.ofile, self.kind, self.arguments)

    def get_full_srcfile(self):
        """ Gets the path of the srcfile relative to SCRIPT_ROOT """
        return os.path.normpath(os.path.join(self.working_dir, self.srcfile))

    def get_full_ofile(self):
        """ Gets the path of the ofile relative to SCRIPT_ROOT """
        return os.path.normpath(os.path.join(self.working_dir, self.ofile))

    @classmethod
    def for_cfile(cls, working_dir, srcfile, ofile, arguments, nonjlm=None):
        """
        Creates a SourceFile instance for a C or C++ file,
        while filtering out arguments that have been marked as being ignored,
        and performing checks.

        If nonjlm is True, the file kind is marked as not to be processed by jlm-opt.
        If nonjlm is None (the default), the NONJLM_C_FILES list is consulted.
        """

        if srcfile.endswith(".c"):
            kind = "C"
        elif srcfile.endswith(".cpp") or srcfile.endswith(".cc"):
            kind = "C++"

        # Let -x override file type
        if "-x" in arguments:
            lang, arguments = extract("-x", arguments)
            if lang in ["c", "C"]:
                kind = "C"
            elif lang in ["c++", "C++"]:
                kind = "C++"
            else:
                raise ValueError(f"Unknown C compiler -x value: {lang}")

        # Remove MF and MT
        if "-MF" in arguments:
            _, arguments = extract("-MF", arguments)
        if "-MT" in arguments:
            _, arguments = extract("-MT", arguments)

        if kind is None:
            raise ValueError(f"Unknown source file type: {srcfile}")

        if "-o" in arguments:
            raise ValueError(f"-o arguments should already be filtered out")

        ignored_arguments = CXX_IGNORED_ARGUMENTS if kind=="C++" else C_IGNORED_ARGUMENTS

        arguments = [arg for arg in arguments if arg not in ignored_arguments]
        arguments = [C_REPLACED_ARGUMENTS.get(arg, arg) for arg in arguments]

        # If nonjlm has not been specified, check the list
        if nonjlm is None:
            nonjlm = any(make_relative_to(os.path.join(working_dir, srcfile), SCRIPT_ROOT).endswith(s) for s in NONJLM_C_FILES)

        if nonjlm:
            kind += "-nonjlm"

        return SourceFile(working_dir, srcfile, ofile, kind, arguments)

    @classmethod
    def for_fortranfile(cls, working_dir, srcfile, ofile, arguments):
        """
        Creates a SourceFile instance for a Fortran file,
        while filtering out arguments that have been marked as being ignored,
        and performing checks.
        """

        if "-o" in arguments:
            raise ValueError(f"-o arguments should already be filtered out")

        arguments = [arg for arg in arguments if arg not in FORTRAN_IGNORED_ARGUMENTS]

        # Remove duplicate arguments, while preserving order
        seen = set()
        def first_instance(arg):
            if arg in seen:
                return False
            seen.add(arg)
            return True
        arguments = [arg for arg in arguments if first_instance(arg)]

        return SourceFile(working_dir, srcfile, ofile, kind="Fortran", arguments=arguments)

class Program:
    """
    Represents a single program linked together from a set of object files.
    The compilation commands for creating the object files are included.
    Finally, an optional validator script is provided for testing the produced binary.
    """
    def __init__(self, folder, srcfiles, linker_workdir, ofiles, elffile=None, linker_arguments=None, validator=None):
        """
        :param folder: the folder in which the program is, relative to SCRIPT_ROOT. Only for information.
        :param srcfiles: a list of SourceFile objects representing compiling files into object files
        :param linker_wordir: the working dir of the linking command, relative to SCRIPT_ROOT
        :param ofiles: a list of linked object file paths, all relative to linker_workdir
        :param elffile: the original name of the linker output, relative to linker_workdir.
                        use None to disable linking.
        :param linker_arguments: extra arguments given to the linker
        :param validator: optional path to validator script, relative to SCRIPT_ROOT
        """

        self.folder = ensure_relative_to(folder, SCRIPT_ROOT)
        self.srcfiles = [srcfile.copy() for srcfile in srcfiles]
        self.linker_workdir = ensure_relative_to(linker_workdir, SCRIPT_ROOT)
        self.ofiles = [ensure_relative_to(ofile, self.linker_workdir) for ofile in ofiles]

        if elffile:
            self.elffile = ensure_relative_to(elffile, self.linker_workdir)
        else:
            self.elffile = None
            # We should not have linker_arguments if we are not linking
            assert linker_arguments is None

        if linker_arguments:
            self.linker_arguments = linker_arguments.copy()
        else:
            self.linker_arguments = []

        if validator:
            self.validator = ensure_relative_to(validator, SCRIPT_ROOT)
        else:
            self.validator = None

        self._remove_ignored_ofiles()
        self._remove_unused_srcfiles()

    def to_dict(self):
        result = {
            "folder": self.folder,
            "srcfiles": [srcfile.to_dict() for srcfile in self.srcfiles],
            "linker_workdir": self.linker_workdir,
            "ofiles": self.ofiles,
        }
        if self.elffile:
            result["elffile"] = self.elffile
            result["linker_arguments"] = self.linker_arguments

        if self.validator:
            result["validator"] = self.validator

        return result

    def _remove_ignored_ofiles(self):
        def keep(ofile):
            ofile_full = make_relative_to(os.path.join(self.linker_workdir, ofile), SCRIPT_ROOT)
            return not any(ofile_full.endswith(ignored) for ignored in IGNORED_OFILES)
        self.ofiles = [ofile for ofile in self.ofiles if keep(ofile)]

    def _remove_unused_srcfiles(self):
        expected_ofiles = set(make_relative_to(os.path.join(self.linker_workdir, ofile), SCRIPT_ROOT) for ofile in self.ofiles)

        seen_ofiles = {}
        def keep(srcfile):
            ofile = srcfile.get_full_ofile()

            if ofile not in expected_ofiles:
                # print(f"Warning: SourceFile ({srcfile.get_full_srcfile()}) produces ofile that is not requested: {ofile}")
                return False

            if ofile in seen_ofiles:
                other = seen_ofiles[ofile]
                print(f"Duplicate SourceFiles ({srcfile.get_full_srcfile()}, {other.get_full_srcfile()}) produce the same ofile: {ofile}")
                return False
            seen_ofiles[ofile] = srcfile

            return True

        self.srcfiles = [srcfile for srcfile in self.srcfiles if keep(srcfile)]

        missing_ofiles = expected_ofiles - seen_ofiles.keys()
        if len(missing_ofiles):
            print("Missing ofiles not provided by any srcfile:")
            for ofile in missing_ofiles:
                print(ofile)


def separate_compiler_arguments_generic(arguments, flags_with_arguments):
    """
    Takes a list of arguments and separates it into flags and positional arguments.
    :param arguments: a list of command arguments (exluding the executable itself)
    :param flags_with_arguments: a list of flags that take a following option
    :returns: a tuple of (flags, positional)

    e.g. with "-I" and "-o" in flags_with_arguments, the input

    ["-c", "-I", "include", "file.c", "-o", "file.o"]

    becomes

    (["-c", "-I", "include", "-o", "file.o"], ["file.c"])
    """

    flags = []
    positional = []
    next_flag = False
    for arg in arguments:
        if arg.startswith("-"):
            flags.append(arg)

            if arg in flags_with_arguments:
                next_flag = True
        elif next_flag:
            flags.append(arg)
            next_flag = False
        else:
            positional.append(arg)

    if next_flag:
        raise ValueError(f"Compile command ended with flag expecting an argument: {arguments}")

    return flags, positional

def separate_c_compiler_arguments(arguments):
    return separate_compiler_arguments_generic(arguments, C_FLAGS_WITH_ARGUMENTS)

def separate_fortran_compiler_arguments(arguments):
    return separate_compiler_arguments_generic(arguments, FORTRAN_FLAGS_WITH_ARGUMENTS)

# ================================================================================
#                Functions for extracting build steps from SPEC2017
# ================================================================================

def parse_cc_command(line, working_dir):
    args = shlex.split(line)
    if len(args) == 0:
        return None

    compiler_name = args[0].split("/")[-1]
    if compiler_name not in C_COMPILERS:
        return None

    flags, positional = separate_c_compiler_arguments(args[1:])

    # If this is not a compilation, skip it
    if "-c" not in flags:
        return None

    ofile, flags = extract("-o", flags)

    if len(positional) != 1:
        raise ValueError(f"Expected exactly one positional arg: {positional}")
    srcfile = positional[0]

    return SourceFile.for_cfile(working_dir, srcfile, ofile, flags)

def parse_fortran_command(line, working_dir):
    args = shlex.split(line)
    if len(args) == 0:
        return None

    compiler_name = args[0].split("/")[-1]
    if compiler_name not in FORTRAN_COMPILERS:
        return None

    flags, positional = separate_fortran_compiler_arguments(args[1:])

    ofile, flags = extract("-o", flags)

    if len(positional) != 1:
        raise ValueError(f"Expected exactly one positional arg: {positional}")
    srcfile = positional[0]

    return SourceFile.for_fortranfile(working_dir, srcfile, ofile, flags)


def parse_link_command(line, working_dir, srcfiles):
    args = shlex.split(line)
    if len(args) == 0:
        raise ValueError()

    linker_name = args[0].split("/")[-1]
    if linker_name not in LINKERS:
        return None

    flags, positional = separate_c_compiler_arguments(args[1:])

    if "-c" in args:
        raise ValueError(f"Not a linking command: {line}")

    elffile, flags = extract("-o", flags)

    return Program(folder=working_dir, srcfiles=srcfiles, linker_workdir=working_dir,
                   ofiles=positional, elffile=elffile, linker_arguments=flags)

def program_from_spec_make(make_out_file):
    make_out_file = make_relative_to(make_out_file, SCRIPT_ROOT)
    working_dir = os.path.dirname(make_out_file)

    # Replace build/build_base-paths from SPEC2017 with src/ to avoid relying on the build folder existsing
    working_dir = re.sub(r'/build/build_base_[^/]*', '/src', working_dir)

    srcfiles = []
    programs = []

    with open(make_out_file, 'r', encoding='utf-8') as make_out_fd:
        for line in make_out_fd:
            srcfile = parse_cc_command(line, working_dir)
            if srcfile is not None:
                srcfiles.append(srcfile)
                continue

            srcfile = parse_fortran_command(line, working_dir)
            if srcfile is not None:
                srcfiles.append(srcfile)
                continue

            program = parse_link_command(line, working_dir, srcfiles)
            if program is not None:
                programs.append(program)

    if len(programs) == 0:
        raise ValueError(f"The file {make_out_file} contained no linking command")
    if len(programs) > 1:
        raise ValueError(f"The file {make_out_file} contained multiple linking commands")
    return programs[0]

def program_from_spec(spec_folder):
    """
    Creates a Program for the given spec benchmark folder, e.g. "502.gcc_r"
    """
    build_dir = os.path.join(SPEC2017_FOLDER, f"{spec_folder}/build/")
    if not os.path.isdir(build_dir):
        raise ValueError(f"The spec benchmark {spec_folder} has not been built before")

    dirlist = os.listdir(build_dir)
    dirlist = [f for f in dirlist if f.startswith("build_base_clang")]
    if len(dirlist) == 0:
        raise ValueError(f"The spec benchmark {spec_folder} has not been built")

    latest_build_dir = os.path.join(build_dir, max(dirlist))

    for make_out_name in ["make.out", f"make.{spec_folder.split('.')[1]}.out"]:
        make_out_file = os.path.join(latest_build_dir, make_out_name)
        if os.path.exists(make_out_file):
            break
    else:
        raise ValueError(f"No make.out or similar file found in {latest_build_dir}")

    return program_from_spec_make(make_out_file)

# =====================================================================
#     Functions for converting SPEC2017 programs to redist2017
# =====================================================================
def redist_program_from_spec(redist_program_name, spec_program):
    """
    Takes the Program object from a spec2017 benchmark and converts it to its named redist version.
    """
    redist_options = REDIST2017_PROGRAMS[redist_program_name]

    old_folder = spec_program.folder
    new_folder = os.path.join(REDIST2017_FOLDER, redist_options["dir"])

    assert not old_folder.endswith("/")
    assert not new_folder.endswith("/")

    def replace(path):
        assert path.startswith(old_folder)
        return path.replace(old_folder, new_folder)

    srcfiles = []
    for old_srcfile in spec_program.srcfiles:
        srcfile = old_srcfile.copy()
        srcfile.working_dir = replace(srcfile.working_dir)
        if os.path.exists(srcfile.get_full_srcfile()):
            srcfiles.append(srcfile)

    if redist_program_name.endswith("538.imagick"):
        # SPEC modifies the magick-config.h file to add these, so we have add them to the commands instead
        for srcfile in srcfiles:
            srcfile.arguments.extend(["-DMAGICKCORE_HDRI_ENABLE=0", "-DMAGICKCORE_QUANTUM_DEPTH=16"])

    kwargs = {
        "folder": new_folder,
        "srcfiles": srcfiles,
        "linker_workdir": replace(spec_program.linker_workdir),
        "ofiles": spec_program.ofiles
    }
    if redist_options["link"]:
        kwargs["elffile"] = spec_program.elffile
        kwargs["linker_arguments"] = spec_program.linker_arguments

    return Program(**kwargs)


# =====================================================================
#      Creates a program using bear's events.json
# =====================================================================
def program_from_folder(folder, data):

    # A regex matching the path of the final output binary
    elffile_regex = data["elffile"]
    # Should we attempt to link the benchmark
    should_link = data.get("link", True)

    # An optional path to a script used to validate the produced binary
    validator = data.get("validator", None)

    events_file = os.path.join(folder, "events.json")
    if not os.path.isfile(events_file):
        raise ValueError(f"The folder {folder} is missing events.json")

    with open(events_file, 'r') as events_fd:
        event_lines = events_fd.readlines()

    # All files compiled during the traced build process
    srcfiles = []

    # Mapping from linker output file to all its inputs
    # All paths relative to SCRIPT_ROOT
    linker_inputs_map = {}

    def collect_linker_inputs_recursive(output_abs):
        ofiles = []

        # Do a DFS starting from the final output file
        stack = [output_abs]
        seen = set(stack)

        while stack:
            top = stack.pop()

            # If the file is itself the result of linking or archiving
            if top in linker_inputs_map:
                for input_file in linker_inputs_map[top][::-1]:
                    if input_file in seen:
                        continue
                    stack.append(input_file)
                    seen.add(input_file)
            else:
                ofiles.append(make_relative_to(os.path.join(SCRIPT_ROOT, top), working_dir))

        return ofiles

    def handle_ar_command(arguments, working_dir):
        if "--help" in arguments:
            return

        while "--plugin" in arguments:
            _, arguments = extract("--plugin", arguments)

        # ar takes the "operation", which is something like "cr" or "cvr"
        assert "c" in arguments[0] and len(arguments[0]) <= 4
        output = arguments[1]
        inputs = arguments[2:]

        output = make_relative_to(os.path.join(working_dir, output), SCRIPT_ROOT)
        inputs = [make_relative_to(os.path.join(working_dir, inp), SCRIPT_ROOT) for inp in inputs]

        # Skip ar commands that link ignored files as well
        if any(inp.endswith(ignored) for inp in inputs for ignored in DISQUALIFYING_FILES):
            return

        linker_inputs_map[output] = inputs

    def handle_cp_command(arguments, working_dir):
        assert len(arguments) == 2

        source, destination = arguments

        source = make_relative_to(os.path.join(working_dir, source), SCRIPT_ROOT)
        destination = make_relative_to(os.path.join(working_dir, destination), SCRIPT_ROOT)

        linker_inputs_map[destination] = [source]

    def handle_compile_command(flags, positional, working_dir):
        if len(positional) != 1:
            raise ValueError(f"Compiler command should have exactly one positional argument: {arguments}")
        srcfile = positional[0]

        # If there is a -o, extract it
        if "-o" in flags:
            ofile, flags = extract("-o", flags)
        else:
            # When no output is specified, the default is to output in the working directory
            ofile = os.path.basename(srcfile)
            assert ofile.endswith(".c")
            ofile = ofile[:-2] + ".o"

        srcfiles.append(SourceFile.for_cfile(working_dir=working_dir,
                                             srcfile=srcfile,
                                             ofile=ofile,
                                             arguments=flags))

    def handle_link_command(flags, positional, working_dir):
        if "-o" not in flags:
            raise ValueError(f"Linking command must have an explicit output file: {arguments}")
        ofile, flags = extract("-o", flags)

        ofile_abs = make_relative_to(os.path.join(working_dir, ofile), SCRIPT_ROOT)

        linker_inputs_map[ofile_abs] = []
        for input_ofile in positional:
            linker_inputs_map[ofile_abs].append(make_relative_to(os.path.join(working_dir, input_ofile), SCRIPT_ROOT))

        # If this is the final linking command, collect all ofiles involved
        if re.search(elffile_regex, ofile_abs):
            # The final set of ofiles, relative to working_dir
            ofiles = collect_linker_inputs_recursive(ofile_abs)

            if should_link:
                elffile = ofile
                linker_arguments=flags
            else:
                elffile = None
                linker_arguments=None

            return Program(folder=folder, srcfiles=srcfiles, linker_workdir=working_dir,
                           ofiles=ofiles, elffile=elffile, linker_arguments=linker_arguments,
                           validator=validator)


    for event_line in event_lines:
        event = json.loads(event_line)

        # Support for the events.json format from bear 3.1.3
        if "started" in event:
            event = event["started"]
        elif "terminated" in event:
            continue

        executable = event["execution"]["executable"]
        arguments = event["execution"]["arguments"][1:]
        working_dir = event["execution"]["working_dir"]

        # Workaround for sendmail naming build folders after the host kernel
        if "sendmail-8.18.1/" in working_dir:
            convert = lambda text: re.sub(r"/obj\.[^/]*/", "/", text).replace("../../", "../")
            working_dir = convert(working_dir)
            arguments = [convert(arg) for arg in arguments]

        if executable == "cp" or executable.endswith("/cp"):
            handle_cp_command(arguments, working_dir)

        if any(executable.endswith(cmd) for cmd in ARCHIVERS):
            handle_ar_command(arguments, working_dir)

        elif any(executable.endswith(c) for c in C_COMPILERS):
            flags, positional = separate_c_compiler_arguments(arguments)

            # Skip commands that were executed only to extract info
            def should_skip_flag(flag):
                return any(re.match(disq, flag) for disq in DISQUALIFYING_FLAGS)
            if any(should_skip_flag(flag) for flag in flags):
                continue

            # Skip commands that compile or link ignored files (also compiled for info)
            def should_skip_filename(filename):
                full_path = os.path.normpath(os.path.join(working_dir, filename))
                return any(full_path.endswith(ignored) for ignored in DISQUALIFYING_FILES)
            if any(should_skip_filename(filename) for filename in positional):
                continue

            if "-c" in flags:
                handle_compile_command(flags, positional, working_dir)
            else:
                program = handle_link_command(flags, positional, working_dir)

                # Was this the final link command we were looking for?
                if program is not None:
                    return program

    raise ValueError(f"No linker command producing {elffile_regex} found in {events_file}")

# =====================================================================
#     Functions for creating build commands for polybench
# =====================================================================
def program_from_polybench(program, main_cfile):
    # All polybench builds are done relative to the root of polybench
    workdir = POLYBENCH_FOLDER

    # The directory containing e.g. atax.c and atax.h
    program_dir = os.path.dirname(main_cfile)

    # Use a fake build folder
    builddir = "build"
    elffile = os.path.join(builddir, main_cfile[:-2])

    arguments = ["-Iutilities", f"-I{program_dir}", "-DPOLYBENCH_TIME", "-DPOLYBENCH_DUMP_ARRAYS"]

    srcfiles = []
    ofiles = []

    def add_cfile(cfile, nonjlm=None):
        ofile = os.path.join(builddir, cfile[:-2]) + ".o"
        srcfile = SourceFile.for_cfile(working_dir=workdir,
                                       srcfile=cfile,
                                       ofile=ofile,
                                       arguments=arguments,
                                       nonjlm=nonjlm)
        srcfiles.append(srcfile)
        ofiles.append(ofile)

    add_cfile(main_cfile)
    add_cfile("utilities/polybench.c", nonjlm=True)

    # Include polybench.c as a linker argument, as we do not care about compiling it separately
    program = Program(folder=workdir, srcfiles=srcfiles, linker_workdir=workdir,
                      ofiles=ofiles, elffile=elffile, linker_arguments=[])

    return program


# =====================================================================
#     Functions for creating build commands for embench
# =====================================================================
def program_from_embench(program, cfiles):
    # All polybench builds are done relative to the root of polybench
    workdir = EMBENCH_FOLDER

    # Invent a fake build folder, since we never actually build here
    builddir = "build"
    elffile = os.path.join(builddir, program)

    arguments = ["-fdata-sections", "-ffunction-sections",
                 "-Isupport", "-Iconfig/native/boards/default", "-Iconfig/native/chips/default", "-Iconfig/native",
                 "-DCPU_MHZ=1","-DWARMUP_HEAT=1"]

    srcfiles = []
    ofiles = []

    def add_cfile(cfile, nonjlm=None):
        ofile = os.path.join(builddir, cfile[:-2]) + ".o"
        srcfile = SourceFile.for_cfile(working_dir=workdir,
                                   srcfile=cfile,
                                   ofile=ofile,
                                   arguments=arguments,
                                    nonjlm=nonjlm)
        srcfiles.append(srcfile)
        ofiles.append(ofile)

    for cfile in cfiles:
        add_cfile(os.path.join("src", cfile))

    SUPPORT_FILES = ["config/native/chips/default/chipsupport.c",
                     "config/native/boards/default/boardsupport.c",
                     "support/main.c",
                     "support/beebsc.c"]

    for cfile in SUPPORT_FILES:
        add_cfile(cfile, nonjlm=True)

    linker_arguments = ["-Wl,-gc-sections", "-lm"]

    # Include support c files as linker arguments, as we do not care about compiling them separately
    program = Program(folder=workdir, srcfiles=srcfiles, linker_workdir=workdir,
                      ofiles=ofiles, elffile=elffile, linker_arguments=linker_arguments,
                      validator=EMBENCH_VALIDATOR)

    return program


def main():
    parser = argparse.ArgumentParser(description='Turn build logs into a sources.json file')
    parser.add_argument('--list', dest='print_list', action='store_true',
                        help="Prints a list of the programs the script can index")
    parser.add_argument('--filter', dest='filter', action='store', default=None,
                        help="Optional regex filter that program names must include")
    parser.add_argument('--output', dest='output', action='store', default='sources.json',
                        help="The name of the destination json file [sources.json]")
    args = parser.parse_args()

    # We can not place the sources.json file anywhere else, as that messes with relative paths
    assert "/" not in args.output

    def should_skip(program):
        # If listing all possible programs, print and skip every program
        if args.print_list:
            print(f" - {program}")
            return True

        return args.filter is not None and not re.search(args.filter, program)

    programs = {}

    for program in SPEC2017_PROGRAMS:
        if should_skip(program):
            continue
        print(f"Indexing program {program}")
        spec_folder = program.replace("cpu2017-", "") + "_r"
        program_object = program_from_spec(spec_folder)
        programs[program] = program_object

        redist_program = program.replace("cpu2017", "redist2017")
        if redist_program in REDIST2017_PROGRAMS:
            if should_skip(redist_program):
                continue
            print(f"Indexing program {redist_program}")
            redist_program_object = redist_program_from_spec(redist_program, program_object)
            programs[redist_program] = redist_program_object

    for program, data in OTHER_PROGRAMS.items():
        if should_skip(program):
            continue
        print(f"Indexing program {program}")
        program_folder_path = os.path.join(PROGRAM_FOLDER, program)
        programs[program] = program_from_folder(program_folder_path, data)

    for program, cfile in POLYBENCH_PROGRAMS.items():
        if should_skip(program):
            continue
        print(f"Indexing program {program}")
        programs[program] = program_from_polybench(program, cfile)

    for program, cfiles in EMBENCH_PROGRAMS.items():
        if should_skip(program):
            continue
        print(f"Indexing program {program}")
        programs[program] = program_from_embench(program, cfiles)


    # If all programs are filtered out, or we are just printing the list, quit now
    if len(programs) == 0:
        return

    with open(args.output, 'w', encoding='utf-8') as output_file:
        json.dump({k: v.to_dict() for k, v in programs.items()}, output_file, indent=2)

if __name__ == "__main__":
    main()
