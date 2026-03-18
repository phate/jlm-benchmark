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

# The script should be run from the sources folder
SCRIPT_ROOT = os.getcwd()

# C++ compilers can also be used to compile / link C, so handle them all
C_COMPILERS = ["clang", "clang18", "gcc", "jlc", "cc", "clang++", "clang++18", "g++"]
LINKERS = C_COMPILERS

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
# This map gives the respective folder names in the redist2017/extracted/ folder
REDIST2017_PROGRAMS = {
    # "redist2017-500.perlbench": "perl-5.22.1",
    "redist2017-502.gcc": "502.gcc_r/src",
    "redist2017-507.cactuBSSN": "507.cactuBSSN_r/src",
    "redist2017-525.x264": "525.x264_r/src",
    "redist2017-526.blender": "526.blender_r/src",
    "redist2017-538.imagick": "ImageMagick-6.8.9-1",
    "redist2017-557.xz": "557.xz_r/src",
    "redist2017-544.nab": "544.nab_r/src"
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

# These programs are located directly in the PROGRAM_FOLDER
# Compilation commands to build and link these programs are extracted from events.json
# The dictionary key is the linker output
OTHER_PROGRAMS = {
    "emacs-29.4": "src/temacs.tmp",
    "ghostscript-10.04.0": "bin/gs",
    "gdb-15.2": "gdb/gdb",
    "sendmail-8.18.1": ""
}

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
    # Just to avoid having a ton of duplicate polybench.c files
    "utilities/polybench.c"
]

# All files whose full path end in one of the following should be skipped entirely
IGNORED_FILES = [
    "conftest.c", # Used by gdb to test the system compiler
    "conftest1.c",
    "conftest2.c",
    "conftest.cpp"
]

# When these flags appear on their own, the next argument belongs to it, and is not a positional argument
FLAGS_WITH_ARGUMENTS = [
    "-I",
    "-include",
    "-D",
    "-o",
    "-x",
    "-MF",
    "-MT",
]

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
    "-gfull"
]

REPLACED_ARGUMENTS = {
    "-fstrict-flex-arrays": "-fstrict-flex-arrays=3"
}

# Commands with arguments that match any of these regexes should be ignored,
# as they are only used by the build system to extract info
DISQUALIFYING_FLAGS = ["-v", "-V", "--?version", "-qversion", "--?print.*"]

def make_relative_to(path, base):
    """
    Makes a path relative to base. Is must be an absolute path, or relative to the SCRIPT_ROOT.
    Asserts that base is a directory.
    """
    if not path.startswith("/"):
        path = os.path.abspath(path)

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
        :param kind: the kind of file. Either "C", "C++" or "C-nonjlm".
        :param arguments: arguments to pass to the compilation command
        """

        # If absolute paths have been provided, make them relative
        self.working_dir = make_relative_to(working_dir, SCRIPT_ROOT)
        self.srcfile = make_relative_to(os.path.join(self.working_dir, srcfile), self.working_dir)
        self.ofile = make_relative_to(os.path.join(self.working_dir, ofile), self.working_dir)
        self.kind = kind
        self.arguments = arguments

        if self.kind not in ["C", "C++", "C-nonjlm"]:
            raise ValueError(f"Unknown SourceFile kind: {kind}")

        full_path = os.path.join(self.working_dir, self.srcfile)
        if not os.path.isfile(full_path):
            raise ValueError(f"source file does not exist: {full_path}")

    def to_dict(self):
        return {
            "working_dir": self.working_dir,
            "srcfile": self.srcfile,
            # In the final output, make ofile relative to script root
            "ofile": make_relative_to(os.path.join(self.working_dir, self.ofile), SCRIPT_ROOT),
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
    def for_cfile(cls, working_dir, srcfile, ofile, arguments):
        """
        Creates a SourceFile instance for a C or C++ file,
        while filtering out arguments that have been marked as being ignored,
        and performing checks.
        """
        kind = None
        if srcfile.endswith(".c"):
            kind = "C"
        elif srcfile.endswith(".cpp") or srcfile.endswith(".cc"):
            kind = "C++"

        # Let -x override file type
        if "-x" in arguments:
            lang, _ = extract("-x", arguments)
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

        arguments = [arg for arg in arguments if arg not in IGNORED_ARGUMENTS]
        arguments = [REPLACED_ARGUMENTS.get(arg, arg) for arg in arguments]

        # Remove duplicate arguments, while preserving order
        arguments = list(set(arguments))

        # If the source file belongs to the list of skipped files,
        # give it a special kind to signal to the benchmarking script to use clang directly
        if any(make_relative_to(os.path.join(working_dir, srcfile), SCRIPT_ROOT).endswith(s) for s in NONJLM_C_FILES):
            kind = "C-nonjlm"

        return SourceFile(working_dir, srcfile, ofile, kind, arguments)

class Program:
    """
    Represents a single program linked together from a set of object files.
    When the object file is the result of compiling a source file, the compilation command is included.
    All ofile paths, and the elffile path, are output relative to SCRIPT_ROOT in the json
    """
    def __init__(self, folder, srcfiles, linker_workdir, ofiles, elffile, linker_arguments):
        """
        :param folder: the folder in which the program is, relative to SCRIPT_ROOT
        :param srcfiles: a list of SourceFile objects representing compiling files into object files
        :param linker_wordir: the working dir of the linking command, relative to SCRIPT_ROOT
        :param ofiles: a list of linked object file paths, all relative to linker_workdir
        :param elffile: the name of the elf output, relative to linker_workdir
        :param linker_arguments: extra arguments given to the linker
        """

        self.folder = folder
        self.srcfiles = [srcfile.copy() for srcfile in srcfiles]
        self.linker_workdir = linker_workdir
        self.ofiles = ofiles.copy()
        self.elffile = elffile
        self.linker_arguments = linker_arguments.copy()

        self.remove_unused_srcfiles()

    def to_dict(self):
        return {
            "srcfiles": [srcfile.to_dict() for srcfile in self.srcfiles],
            "linker_workdir": self.linker_workdir,
            "ofiles": [make_relative_to(os.path.join(self.linker_workdir, ofile), SCRIPT_ROOT) for ofile in self.ofiles],
            "elffile": make_relative_to(os.path.join(self.linker_workdir, self.elffile), SCRIPT_ROOT),
            "linker_arguments": self.linker_arguments
            }

    def remove_unused_srcfiles(self):
        expected_ofiles = set(make_relative_to(os.path.join(self.linker_workdir, ofile), SCRIPT_ROOT) for ofile in self.ofiles)

        seen_ofiles = {}
        def keep(srcfile):
            ofile = srcfile.get_full_ofile()

            if ofile not in expected_ofiles:
                print(f"Skipping SourceFile ({srcfile.get_full_srcfile()}) due to ofile not being requested: {ofile}")
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


def separate_compiler_arguments(arguments):
    """
    Takes a list of arguments (exluding the executable itself),
    and separates it into flags and positional arguments.
    :returns: a tuple of (flags, positional)

    e.g. ["-c", "-I", "include", "file.c", "-o", "file.o"]

    becomes

    (["-c", "-I", "include", "-o", "file.o"], ["file.c"])
    """

    flags = []
    positional = []
    next_flag = False
    for arg in arguments:
        if arg.startswith("-"):
            flags.append(arg)

            if arg in FLAGS_WITH_ARGUMENTS:
                next_flag = True
        elif next_flag:
            flags.append(arg)
            next_flag = False
        else:
            positional.append(arg)

    if next_flag:
        raise ValueError(f"Compile command ended with flag expecting an argument: {arguments}")

    return flags, positional

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

    flags, positional = separate_compiler_arguments(args[1:])

    # If this is not a compilation, skip it
    if "-c" not in flags:
        return None

    ofile, flags = extract("-o", flags)

    if len(positional) != 1:
        raise ValueError(f"Expected exactly one positional arg: {positional}")
    srcfile = positional[0]

    return SourceFile.for_cfile(working_dir, srcfile, ofile, flags)

def parse_link_command(line, working_dir, srcfiles):
    args = shlex.split(line)
    if len(args) == 0:
        raise ValueError()

    linker_name = args[0].split("/")[-1]
    if linker_name not in LINKERS:
        return None

    flags, positional = separate_compiler_arguments(args[1:])

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
    dirlist = [f for f in dirlist if f.startswith("build")]
    if len(dirlist) == 0:
        raise ValueError(f"The spec benchmark {spec_folder} has not been built before")

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
    old_folder = spec_program.folder
    new_folder = os.path.join(REDIST2017_FOLDER, REDIST2017_PROGRAMS[redist_program_name])

    assert not old_folder.endswith("/")
    assert not new_folder.endswith("/")

    def replace(path):
        assert path.startswith(old_folder)
        return path.replace(old_folder, new_folder)

    srcfiles = []
    for old_srcfile in spec_program.srcfiles:
        srcfile = old_srcfile.copy()
        srcfile.working_dir = replace(srcfile.working_dir)
        srcfiles.append(srcfile)

    linker_workdir = replace(spec_program.linker_workdir)

    if redist_program_name.endswith("538.imagick"):
        # SPEC modifies the magick-config.h file to add these, so we have add them to the commands instead
        for srcfile in srcfiles:
            srcfile.arguments.extend(["-DMAGICKCORE_HDRI_ENABLE=0", "-DMAGICKCORE_QUANTUM_DEPTH=16"])

    return Program(folder=new_folder, srcfiles=srcfiles, linker_workdir=linker_workdir,
                   ofiles=spec_program.ofiles,
                   elffile=spec_program.elffile,
                   linker_arguments=spec_program.linker_arguments)

# =====================================================================
#     Functions for creating build commands for polybench
# =====================================================================
def program_from_polybench(program, main_cfile):
    # All polybench builds are done relative to the root of polybench
    workdir=POLYBENCH_FOLDER

    # The directory containing e.g. atax.c and atax.h
    program_dir=os.path.dirname(main_cfile)

    # Invent a fake build folder, since we never actually build polybench here
    builddir=os.path.join(workdir, "build")

    srcfiles = []
    ofiles = []

    def add_cfile(cfile):
        # relative to builddir
        ofile = cfile[:-2] + ".o"
        ofiles.append(ofile)

        ofile_relative_to_workdir = os.path.join("build", ofile)
        srcfiles.append(SourceFile.for_cfile(working_dir=workdir,
                                             srcfile=cfile,
                                             ofile=ofile_relative_to_workdir,
                                             arguments=["-Iutilities", f"-I{program_dir}", "-DPOLYBENCH_TIME", "-DPOLYBENCH_DUMP_ARRAYS"]))

    add_cfile(main_cfile)
    add_cfile("utilities/polybench.c")

    # Relative to builddir
    elffile = main_cfile[:-2] # Remove .c to get a suitable binary name

    program = Program(folder=workdir, srcfiles=srcfiles, linker_workdir=builddir,
                      ofiles=ofiles, elffile=elffile, linker_arguments=[])

    return program


# =====================================================================
#      Creates a program using bear's events.json
# =====================================================================
def program_from_folder(folder):

    events_file = os.path.join(folder, "events.json")
    if not os.path.isfile(events_file):
        raise ValueError(f"The folder {folder} is missing events.json")

    with open(events_file, 'r') as events_fd:
        event_lines = events_fd.readlines()

    srcfiles = []
    linker_workdir = None
    ofiles = []
    elffile = None
    linker_arguments = None
    for event_line in event_lines:
        event = json.loads(event_line)
        executable = event["execution"]["executable"]
        arguments = event["execution"]["arguments"][1:]
        working_dir = event["execution"]["working_dir"]

        if not any(executable.endswith(c) for c in C_COMPILERS):
            # Skip commands that are not a compiler
            continue

        flags, positional = separate_compiler_arguments(arguments)

        # Skip commands that were executed only for info
        def should_skip_flag(flag):
            return any(re.match(disq, flag) for disq in DISQUALIFYING_FLAGS)
        if any(should_skip_flag(flag) for flag in flags):
            continue

        # Skip commands that compile or link ignored files
        def should_skip_posit(posit):
            full_path = os.path.normpath(os.path.join(working_dir, posit))
            return any(full_path.endswith(ignored) for ignored in IGNORED_FILES)
        if any(should_skip_posit(posit) for posit in positional):
            continue


        # If there is a -o, remove it
        if "-o" in flags:
            ofile, flags = extract("-o", flags)
        else:
            ofile = None

        # Is this a linking command or a compilation command?
        if "-c" in flags:
            if len(positional) != 1:
                raise ValueError(f"Compiler command should have exactly one positional argument: {arguments}")
            srcfile = positional[0]

            if ofile is None:
                assert "." in srcfile
                ofile = srcfile[:srcfile.rfind(".")] + ".o"

                srcfile = SourceFile.for_cfile(working_dir=working_dir,
                                               srcfile=srcfile,
                                               ofile=ofile,
                                               arguments=flags)
                srcfiles.append(srcfile)
        else:
            # This is a linking command
            if ofile is None:
                raise ValueError(f"Linking command can not have a deafult output file: {arguments}")

            if elffile is not None:
                print(f"We already had a linker output: {elffile}")

            elffile = ofile
            ofiles = positional
            linker_workdir = working_dir
            linker_arguments = flags

    if elffile is None:
        raise ValueError(f"No linking command seen in benchmark {folder}")
    program = Program(folder=folder, srcfiles=srcfiles, linker_workdir=linker_workdir,
                      ofiles=ofiles, elffile=elffile, linker_arguments=linker_arguments)

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
        print(f"Trying to index program {program}")
        spec_folder = program.replace("cpu2017-", "") + "_r"
        program_object = program_from_spec(spec_folder)
        programs[program] = program_object

        redist_program = program.replace("cpu2017", "redist2017")
        if redist_program in REDIST2017_PROGRAMS:
            if should_skip(redist_program):
                continue
            print(f"Trying to index program {redist_program}")
            redist_program_object = redist_program_from_spec(redist_program, program_object)
            programs[redist_program] = redist_program_object

    for program, cfile in POLYBENCH_PROGRAMS.items():
        if should_skip(program):
            continue
        print(f"Trying to index program {program}")
        program_object = program_from_polybench(program, cfile)
        programs[program] = program_object

    for program in OTHER_PROGRAMS:
        if should_skip(program):
            continue
        print(f"Trying to index program {program}")
        program_folder_path = os.path.join(PROGRAM_FOLDER, program)
        program_object = program_from_folder(program_folder_path)
        programs[program] = program_object

    # If all programs are filtered out, or we are just printing the list, quit now
    if len(programs) == 0:
        return

    with open(args.output, 'w', encoding='utf-8') as output_file:
        json.dump({k: v.to_dict() for k, v in programs.items()}, output_file, indent=2)

if __name__ == "__main__":
    main()
