#!/usr/bin/env python3
import os
import os.path
import subprocess
import sys
import shutil
import datetime
import time
import argparse
import re
import tempfile
import threading
import concurrent.futures
import queue
import json
import functools
import traceback

class TaskTimeoutError(Exception):
    pass

class TaskSubprocessError(Exception):
    pass

class Options:
    DEFAULT_BUILD_DIR = "build/default/"
    DEFAULT_STATS_DIR = "statistics/default/"
    DEFAULT_JLM_OPT_VERBOSITY = 1

    def __init__(self, llvm_bindir, build_dir, stats_dir, jlm_opt, jlm_opt_verbosity, timeout):
        self.llvm_bindir = llvm_bindir
        self.clang = os.path.join(llvm_bindir, "clang")
        self.clang_link = os.path.join(llvm_bindir, "clang++")
        self.opt = os.path.join(llvm_bindir, "opt")
        self.llvm_link = os.path.join(llvm_bindir, "llvm-link")

        self.build_dir = build_dir
        self.stats_dir = stats_dir

        self.jlm_opt = jlm_opt
        self.jlm_opt_verbosity = jlm_opt_verbosity

        # Allow setting a timeout on running subprocesses. In seconds.
        # When reached, the task's action function raises a TaskTimeoutError
        # Any other task that relies on the output of the task is skipped
        self.timeout = timeout

    def get_build_dir(self, filename=""):
        return os.path.abspath(os.path.join(self.build_dir, filename))

    def get_stats_dir(self, filename=""):
        return os.path.abspath(os.path.join(self.stats_dir, filename))


options: Options = None

def run_command(args, cwd=None, env_vars=None, *, verbose=0, print_prefix="", timeout=None):
    """
    Runs the given command, with the given environment variables set.
    :param verbose: how much output to provide
     - 0 no output unless the command fails, in which case stdout and stderr are printed
     - 1 if no new output has been produced in 1 minute, the last line is printed. Stderr is always printed.
     - 2 prints the command being run, as well as all output immediately
    :param timeout: the timeout for the command, in seconds. If reached, TaskTimeoutError is raised
    """
    assert verbose in [0, 1, 2]

    if verbose >= 2:
        print(f"# {' '.join(args)}")

    kwargs = {}
    if verbose in [0, 1]:
        kwargs["stdout"] = subprocess.PIPE
    if verbose == 0:
        kwargs["stderr"] = subprocess.PIPE
    process = subprocess.Popen(args, cwd=cwd, env=env_vars, text=True, bufsize=1, **kwargs)

    if verbose == 1:
        # Use a queue and a separate thread to send lines as they come
        qu = queue.Queue()
        def enqueue_output():
            for line in process.stdout:
                qu.put(line.strip('\n'))
            qu.put(None)
        threading.Thread(target=enqueue_output, daemon=True).start()

        # Make note of the start time to handle timeouts
        start_time = time.time()
        read_lines = 0
        line = ""
        while line is not None:

            # Check if we have timed out
            if timeout is not None and time.time() - start_time > timeout:
                process.kill()
                raise TaskTimeoutError()

            try:
                line = qu.get(timeout=min(60, timeout if timeout else 60))
                read_lines += 1
            except queue.Empty:
                if read_lines == 0:
                    continue
                print_line = f"{print_prefix}: {datetime.datetime.now().strftime('%b %d. %H:%M:%S')}: "
                if read_lines > 1:
                    print_line += f"[Skip {read_lines - 1}] "
                print_line += line
                print(print_line, flush=True)
                read_lines = 0

        # If we had a timeout, remove the time already spent
        if timeout is not None:
            timeout = timeout - (time.time() - start_time)
            timeout = max(timeout, 1)

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        raise TaskTimeoutError()

    if process.returncode != 0:
        print(f"Command failed: {args} with returncode: {process.returncode}")
        if stdout is not None:
            print(f"Stdout:", stdout)
        if stderr is not None:
            print(f"Stderr:", stderr)
        raise TaskSubprocessError()


class Task:
    def __init__(self, *, name, input_files, output_files, action):
        self.name = name
        self.input_files = input_files
        self.output_files = output_files
        self.action = action

    def run(self):
        self.action(self)


def can_skip_task(task):
    """
    Returns true if all outputs of the given task already exist.
    """
    all_outputs_exist = all(os.path.exists(of) for of in task.output_files)

    if all_outputs_exist:
        return True

    return False


def run_all_tasks(tasks, workers=1, dryrun=False):
    """
    Runs all tasks in the given list.
    Assumes that tasks have already been assigned a global index.
    :dryrun: If true, do not actually run any tasks
    :return: three lists of tasks: tasks_finished, tasks_timed_out, tasks_skipped
    """

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    # Indices of tasks that have been submitted, or will never be submitted due to depending on a timed out task
    submitted_tasks = set()
    # Output files of some task that has not finished
    files_not_ready = set()
    # Output files that will never arrive, due to some task it depends on failing or timing out
    skippable_out_files = set()

    tasks_finished = []
    tasks_failed = []
    tasks_timed_out = []
    tasks_skipped = []

    # First make a pass across all tasks, marking all output files as not ready
    for task in tasks:
        # Mark all outputs as not ready
        for output_file in task.output_files:
            if output_file in files_not_ready:
                print(f"error: Multiple tasks produce the output file {output_file}")
                exit(1)
            files_not_ready.add(output_file)

    def run_task(i, task):
        prefix = f"[{i+1}/{len(tasks)}] ({task.index}) {task.name}"
        if dryrun:
            print(f"{prefix} (dry-run)")
        else:
            print(f"{prefix} starting...", flush=True)
            task_start_time = datetime.datetime.now()
            try:
                task.run()
            except TaskTimeoutError:
                task_duration = (datetime.datetime.now() - task_start_time)
                print(f"{prefix} timed out after {task_duration}!", flush=True)
                tasks_timed_out.append(task)
                skippable_out_files.update(task.output_files)
                return
            except TaskSubprocessError:
                tasks_failed.append(task)
                skippable_out_files.update(task.output_files)
                return
            except Exception as e:
                print(e)
                traceback.print_exc()
                tasks_failed.append(task)
                skippable_out_files.update(task.output_files)
                return
            else:
                task_duration = (datetime.datetime.now() - task_start_time)
                print(f"{prefix} took {task_duration}", flush=True)

        tasks_finished.append(task)
        # Remove all output files from not_ready
        for output_file in task.output_files:
            files_not_ready.remove(output_file)

    running_futures = set()

    # All tasks where none of the input files are in files_not_ready can be submitted
    while len(submitted_tasks) < len(tasks):
        for i, task in enumerate(tasks):
            if i in submitted_tasks:
                continue

            # Check if this task depends on any files that have been declared timed out, and thus will never arrive
            if any(input_file in skippable_out_files for input_file in task.input_files):
                print(f"({task.index}) {task.name} is skipped due to depending on a failed or timed out task", flush=True)
                skippable_out_files.update(task.output_files)
                submitted_tasks.add(i)
                tasks_skipped.append(task)
                continue

            if any(input_file in files_not_ready for input_file in task.input_files):
                continue

            # submit it!
            submitted_tasks.add(i)
            running_futures.add(executor.submit(run_task, i, task))

        wait = concurrent.futures.wait(running_futures, return_when=concurrent.futures.FIRST_COMPLETED)
        running_futures = wait.not_done

        # Check if any of the finished futures raised an exception, and abort
        for d in wait.done:
            if d.exception() is not None:
                raise d.exception()

    # Wait for all tasks to finish
    executor.shutdown(wait=True)

    assert len(tasks_finished) + len(tasks_failed) + len(tasks_timed_out) + len(tasks_skipped) == len(tasks)
    return (tasks_finished, tasks_failed, tasks_timed_out, tasks_skipped)


####################################################################
################ Code specific to benchmarking jlm #################
####################################################################

def move_output_files(temp_dir, stats_output, other_outputs):
    """
    Moves files from temp_dir
    Looks for a file called xxxxx-statistics.log, and moves it to stats_output
    All other files with identical xxxx part are moved, given a name consiting of <other_outputs> + <suffix>
    """

    stats_files = []
    other_files = []
    for fil in os.listdir(temp_dir):
        if fil.endswith("-statistics.log"):
            stats_files.append(fil)
        else:
            other_files.append(fil)

    if len(stats_files) > 1:
        raise ValueError(f"Too many statistics files in {temp_dir}!")
    elif len(stats_files) == 0:
        # Create an empty statistics file
        open(stats_output, "w", encoding="utf-8").close()
        if len(other_files) > 0:
            raise ValueError(f"No statistics.log file was produced, but other output files were!")
        return

    stats_file, = stats_files
    # Move the statistics file
    shutil.move(os.path.join(temp_dir, stats_file), stats_output)

    # Move all other files that have the same basename
    basename = stats_file[:-len("-statistics.log")]
    for other_file in other_files:
        if not other_file.startswith(basename):
            continue
        suffix = other_file[len(basename):]
        shutil.move(os.path.join(temp_dir, other_file), other_outputs + suffix)


def clean_temp_dir(temp_dir):
    # Remove all other files in the tmp folder, to prevent buildup
    for fil in os.listdir(temp_dir):
        os.remove(os.path.join(temp_dir, fil))


def ensure_folder_exists(path):
    if os.path.exists(path):
        return
    try:
        os.mkdir(path)
    except FileExistsError as e:
        pass # Someone else made the folder, no biggie


def compile_file(tasks, full_name, workdir, cfile, extra_clang_flags, stats_dir,
                 env_vars=None, opt_flags=None, jlm_opt_flags=None, jlm_opt_suffix=None):
    """
    Creates tasks for compiling the given file with the given arguments to clang.
    :param tasks: the list of tasks to append commands to
    :param full_name: should be a valid filename, unique to the program and source file
    :param workdir: the dir from which clang is invoked
    :param cfile: the name of the c file, relative to workdir
    :param extra_clang_flags: the flags to pass to clang when making the .ll file
    :param stats_dir: the directory to place statistics files in
    :param env_vars: environment variables passed to the executed commands
    :param opt_flags: if not None, opt is run with the given flags
    :param jlm_opt_flags: if not None, jlm-opt is run with the given flags
    :param jlm_opt_suffix: an extra suffix added to output filenames
    :return: a tuple with paths to (clang's output, opt's output, jlm-opt's output)
    """
    assert "/" not in full_name

    if jlm_opt_suffix is None:
        jlm_opt_suffix = ""

    clang_out = options.get_build_dir(f"{full_name}-clang-out.ll")
    opt_out = options.get_build_dir(f"{full_name}-opt-out.ll")
    jlm_opt_out = options.get_build_dir(f"{full_name}{jlm_opt_suffix}-jlm-opt-out.ll")
    stats_output = os.path.join(stats_dir, f"{full_name}{jlm_opt_suffix}.log")
    other_outputs = os.path.join(stats_dir, f"{full_name}{jlm_opt_suffix}")

    combined_env_vars = os.environ.copy()
    if env_vars is not None:
        combined_env_vars.update(env_vars)

    clang_command = [options.clang,
                     "-c", cfile,
                     "-S", "-emit-llvm",
                     "-o", clang_out,
                     *extra_clang_flags]
    tasks.append(Task(name=f"Compile {full_name} to LLVM IR",
                      input_files=[cfile],
                      output_files=[clang_out],
                      action=lambda task: run_command(clang_command, cwd=workdir, env_vars=combined_env_vars, timeout=options.timeout)))

    if opt_flags is not None:
        # use --debug-pass-manager to print more pass info
        opt_command = [options.opt, clang_out, "-S", "-o", opt_out, *opt_flags]
        tasks.append(Task(name=f"opt {full_name}",
                          input_files=[clang_out],
                          output_files=[opt_out],
                          action=lambda task: run_command(opt_command, env_vars=combined_env_vars, timeout=options.timeout)))
    else:
        opt_out = clang_out

    if jlm_opt_flags is not None:
        def jlm_opt_action(task):
            with tempfile.TemporaryDirectory(suffix="jlm-bench") as tmpdir:
                jlm_opt_command = [options.jlm_opt, opt_out, "-o", jlm_opt_out, "-s", tmpdir, *jlm_opt_flags]
                run_command(jlm_opt_command, env_vars=combined_env_vars, verbose=options.jlm_opt_verbosity,
                            print_prefix=f"({task.index})", timeout=options.timeout)
                move_output_files(tmpdir, stats_output, other_outputs)
                clean_temp_dir(tmpdir)

        tasks.append(Task(name=f"jlm-opt {full_name}{jlm_opt_suffix}",
                          input_files=[opt_out],
                          output_files=[jlm_opt_out, stats_output],
                          action=jlm_opt_action))
    else:
        jlm_opt_out = opt_out

    return (clang_out, opt_out, jlm_opt_out)

def link_and_optimize(tasks, full_name, llfiles, direct_ofiles, stats_dir,
                      env_vars=None, llvm_link_flags=None, opt_flags=None, jlm_opt_flags=None, clang_link_output=None, clang_link_workdir=None, clang_link_flags=None):
    """
    Links together the given files. The files can be LLVM IR files or object files.
    opt and jlm-opt can only be used if llvm-link is enabled.
    If llvm-link is not enabled, the final clang command will be given all the input files.

    :param tasks: the list of tasks to append commands to
    :param full_name: should be a valid filename, unique to the program
    :param llfiles: a list of LLVM IR/bitcode files, relative to CWD
    :param direct_ofiles: a list of object files, relative to CWD
    :param stats_dir: the directory to place statistics files in
    :param env_vars: environment variables passed to the executed commands
    :param llvm_link_flags: if not None, llvm-link is run with the given flags
    :param opt_flags: if not None, opt is run with the given flags
    :param jlm_opt_flags: if not None, jlm-opt is run with the given flags
    :param clang_link_output: the path of the final linked binary
    :param clang_link_workdir: the directory to run the final clang linking command from
    :param clang_link_flags: if not None, clang is used to create a binary
    :return: a tuple with paths to (llvm-link's output, opt's output, jlm-opt's output, clang's final output)
    """
    assert "/" not in full_name

    llvm_link_out = options.get_build_dir(f"{full_name}-llvm-link-out.ll")
    opt_out = options.get_build_dir(f"{full_name}-opt-out.ll")
    jlm_opt_out = options.get_build_dir(f"{full_name}-jlm-opt-out.ll")

    combined_env_vars = os.environ.copy()
    if env_vars is not None:
        combined_env_vars.update(env_vars)

    if llvm_link_flags is not None:
        llvm_link_command = [options.llvm_link, "-S",
                             *llfiles, "-o", llvm_link_out, *llvm_link_flags]
        tasks.append(Task(name=f"llvm-link {full_name}",
                          input_files=llfiles,
                          output_files=[llvm_link_out],
                          action=lambda task: run_command(llvm_link_command, env_vars=combined_env_vars, timeout=options.timeout)))

        if opt_flags is not None:
            # use --debug-pass-manager to print more pass info
            opt_command = [options.opt, llvm_link_out, "-S", "-o", opt_out, *opt_flags]
            tasks.append(Task(name=f"opt {full_name}",
                              input_files=[llvm_link_out],
                              output_files=[opt_out],
                              action=lambda task: run_command(opt_command, env_vars=combined_env_vars, timeout=options.timeout)))
        else:
            opt_out = llvm_link_out

        if jlm_opt_flags is not None:
            assert llvm_link_flags is not None

            def jlm_opt_action(task):
                with tempfile.TemporaryDirectory(suffix="jlm-bench") as tmpdir:
                    jlm_opt_command = [options.jlm_opt, opt_out, "-o", jlm_opt_out, "-s", tmpdir, *jlm_opt_flags]
                    run_command(jlm_opt_command, env_vars=combined_env_vars, verbose=options.jlm_opt_verbosity,
                                print_prefix=f"({task.index})", timeout=options.timeout)
                    move_stats_file(tmpdir, stats_output)

            tasks.append(Task(name=f"jlm_opt {full_name}",
                              input_files=[opt_out],
                              output_files=[jlm_opt_out],
                              action=jlm_opt_action))

        else:
            jlm_opt_out = opt_out

        llfiles = [jlm_opt_out]
    else:
        # Without llvm-link, opt and jlm-opt can not be used
        assert opt_flags is None and jlm_opt_flags is None

    if clang_link_output is not None:
        if clang_link_workdir is None:
            clang_link_workdir = "."
        if clang_link_flags is None:
            clang_link_flags = []
        clang_link_workdir = os.path.abspath(clang_link_workdir)

        clang_command = [options.clang_link, *llfiles, *direct_ofiles, "-o", clang_link_output, *clang_link_flags]
        tasks.append(Task(name=f"clang (link) {full_name}",
                          input_files=[*llfiles, *direct_ofiles],
                          output_files=[clang_link_output],
                          action=lambda task: run_command(clang_command, cwd=clang_link_workdir, env_vars=combined_env_vars, timeout=options.timeout)))

    return (llvm_link_out, opt_out, jlm_opt_out, clang_link_output)

def find_common_prefix(strings):
    prefix, *rest = strings
    for string in rest:
        while not string.startswith(prefix):
            prefix = prefix[:-1]
    return prefix

class SourceFile:
    def __init__(self, working_dir, srcfile, ofile, kind, arguments):
        """
        :param working_dir: the folder from which to invoke the compiler, relative to CWD
        :param srcfile: the source file to compile, relative to working_dir
        :param ofile: the ofile originally produced by this command, relative to working_dir
        :param kind: the kind of file
        :param arguments: flags to pass to the compiler
        """
        self.working_dir = working_dir
        self.srcfile = srcfile
        self.ofile = ofile
        self.kind = kind
        self.arguments = arguments

    def get_abspath(self):
        return os.path.abspath(os.path.join(self.working_dir, self.srcfile))

    def get_ofile_abspath(self):
        return os.path.abspath(os.path.join(self.working_dir, self.ofile))

class Benchmark:
    def __init__(self, name, srcfiles, ofiles, linker_output=None, linker_workdir=None, linker_arguments=None, validator=None):
        """
        Constructs a benchmark representing a single program.
        The input passed to this constructor represents the "standard" compile+link pipeline.
        This can be customized by modifying the fields on the constructed class.

        :param name: the name of the program
        :param srcfiles: a list of instances of SourceFile
        :param ofiles: the list of object files to be linked, relative to linker_workdir
        :param linker_output: the name of the final binary, or None to disable linking
        :param linker_workdir: the folder to run the final linking command in
        :param linker_arguments: list of flags to pass to linker
        :param validator: script for validating the final linked output
        """
        self.name = name
        self.srcfiles = srcfiles
        self.ofiles = [os.path.abspath(os.path.join(linker_workdir, ofile)) for ofile in ofiles]

        # Avoid including parts of the source paths that are shared between all sourcefiles in the program
        self.common_abspath = find_common_prefix(srcfile.get_abspath() for srcfile in self.srcfiles)

        # Per C-file compilation and optimization flags
        # Flags passed to clang when compiling to LLVM IR
        self.extra_clang_flags = []
        # Flags passed to clang when compiling C files that are not processed by jlm
        self.extra_clang_flags_nonjlm = ["-O2"]
        # Flags passed to clang when compiling C++ files (not processed by jlm)
        self.extra_clang_flags_cpp = ["-O2"]

        # If set, opt and/or jlm-opt are used
        self.opt_flags = None
        self.jlm_opt_flags = None

        # Whole program optimization and linking flags
        # If set, llvm-link is used
        self.llvm_link_flags = None
        # If set, the output of llvm-link is passed to opt
        self.linked_opt_flags = None
        # If set, the output of the above is passed to jlm-opt
        self.linked_jlm_opt_flags = None
        # The final invocation of clang for linking, resulting in an executable
        if linker_output is not None:
            self.clang_link_output = options.get_build_dir(linker_output)
        else:
            # None disables linking
            self.clang_link_output = None
        self.clang_link_workdir = linker_workdir
        self.clang_link_flags = linker_arguments

        # Add an optional suffix to outputs of jlm-opt
        self.jlm_opt_suffix = None

        # Optional validation script
        self.validator = validator

    def get_full_srcfile_name(self, srcfile):
        """Get a cfile name, including the program name, and enough of the path to make it unique"""
        abspath = srcfile.get_abspath()
        assert abspath.startswith(self.common_abspath)
        path = abspath[len(self.common_abspath):]
        return f"{self.name}+{path}".replace("/", "_")

    def get_tasks(self, stats_dir, env_vars):
        tasks = []

        # Maps from the ofile name used in sources, to the output file produced by jlm-opt
        ofile_to_llfile = {}

        for i, srcfile in enumerate(self.srcfiles):
            full_name = self.get_full_srcfile_name(srcfile)

            if srcfile.kind == "C":
                _, _, outfile = compile_file(tasks, full_name=full_name, workdir=srcfile.working_dir, cfile=srcfile.srcfile,
                                             stats_dir=stats_dir, env_vars=env_vars,
                                             extra_clang_flags=[*self.extra_clang_flags, *srcfile.arguments],
                                             opt_flags=self.opt_flags,
                                             jlm_opt_flags=self.jlm_opt_flags,
                                             jlm_opt_suffix=self.jlm_opt_suffix)

                ofile_to_llfile[srcfile.get_ofile_abspath()] = outfile

            elif srcfile.kind == "C-nonjlm":
                # Compile to LLVM IR, but skip jlm-opt
                _, _, outfile = compile_file(tasks, full_name=full_name, workdir=srcfile.working_dir, cfile=srcfile.srcfile,
                                             stats_dir=stats_dir, env_vars=env_vars,
                                             extra_clang_flags=[*self.extra_clang_flags_nonjlm, *srcfile.arguments],
                                             opt_flags=self.opt_flags)

                ofile_to_llfile[srcfile.get_ofile_abspath()] = outfile

            elif srcfile.kind == "C++" or srcfile.kind == "C++-nonjlm":
                # Compile C++ to LLVM IR, no not use jlm-opt in any case
                _, _, outfile = compile_file(tasks, full_name=full_name, workdir=srcfile.working_dir, cfile=srcfile.srcfile,
                                             stats_dir=stats_dir, env_vars=env_vars,
                                             extra_clang_flags=[*self.extra_clang_flags_cpp, *srcfile.arguments],
                                             opt_flags=self.opt_flags)

                ofile_to_llfile[srcfile.get_ofile_abspath()] = outfile

            else:
                raise ValueError(f"Unknown SourceFile kind: {srcfile.kind}")


        # Try as much as possible to use the LLVM IR files produced above when linking
        llfiles = []
        direct_ofiles = []
        for ofile in self.ofiles:
            if ofile in ofile_to_llfile:
                llfiles.append(ofile_to_llfile[ofile])
            else:
                direct_ofiles.append(ofile)

        link_and_optimize(tasks, full_name=self.name, llfiles=llfiles, direct_ofiles=direct_ofiles,
                          stats_dir=stats_dir, env_vars=env_vars,
                          llvm_link_flags=self.llvm_link_flags,
                          opt_flags=self.linked_opt_flags,
                          jlm_opt_flags=self.linked_jlm_opt_flags,
                          clang_link_output=self.clang_link_output,
                          clang_link_workdir=self.clang_link_workdir,
                          clang_link_flags=self.clang_link_flags)

        return tasks


def get_benchmarks(sources_json):
    """ Returns benchmarks to be compiled """

    # Everything in the sources file is relative to the sources file, so add its path
    sources_folder = os.path.dirname(sources_json)

    benchmarks = []

    with open(sources_json, 'r') as sources_fd:
        programs = json.load(sources_fd)

    for name, data in programs.items():
        srcfiles = []
        for srcfile_data in data["srcfiles"]:
            working_dir = os.path.join(sources_folder, srcfile_data["working_dir"])
            srcfile = srcfile_data["srcfile"]
            ofile = srcfile_data["ofile"]
            kind = srcfile_data["kind"]
            arguments = srcfile_data["arguments"]
            srcfiles.append(SourceFile(working_dir=working_dir, srcfile=srcfile, ofile=ofile, kind=kind, arguments=arguments))

        if len(srcfiles) == 0:
            print(f"Skipping benchmark {name} as it contains no files")
            continue

        ofiles = data["ofiles"]
        linker_output = name
        linker_workdir = os.path.join(sources_folder, data["linker_workdir"])
        linker_arguments = data["linker_arguments"]

        validator = data.get("validator", None)
        if validator is not None:
            validator = os.path.join(sources_folder, validator)

        if len(ofiles) == 0:
            # Disable linking if we have not tracked linking properly
            linker_output = None

        benchmarks.append(Benchmark(name=name,
                                    srcfiles=srcfiles,
                                    ofiles=ofiles,
                                    linker_output=linker_output,
                                    linker_workdir=linker_workdir,
                                    linker_arguments=linker_arguments,
                                    validator=validator))

    # Sort benchmarks in order of ascending number of source files
    benchmarks.sort(key=lambda bench: len(bench.srcfiles))

    return benchmarks


def run_benchmarks(benchmarks,
                   env_vars,
                   offset=0,
                   limit=float('inf'),
                   stride=1,
                   eager=False,
                   workers=1,
                   dryrun=False):
    """
    Creates tasks for all the given benchmarks and executes them.
    Subsets of tasks can be executed by using offsets, limits and strides.
    Returns 1 if any tasks timed out, 0 otherwise
    """
    start_time = datetime.datetime.now()

    tasks = [task for bench in benchmarks for task in bench.get_tasks(options.get_stats_dir(), env_vars)]
    for i, task in enumerate(tasks):
        task.index = i

    if offset != 0:
        tasks = tasks[offset:]
        print(f"Skipping first {offset} tasks, leaving {len(tasks)}")
    if stride != 1:
        tasks = tasks[::stride]
        print(f"Skipping {stride-1} tasks between each task, leaving {len(tasks)}")
    if limit < len(tasks):
        print(f"Limited to {limit} tasks, skipping last {len(tasks)-limit}")
        tasks = tasks[:limit]

    if not eager:
        pre_skip_len = len(tasks)
        tasks = [task for task in tasks if not can_skip_task(task)]
        if len(tasks) != pre_skip_len:
            print(f"Skipping {pre_skip_len - len(tasks)} tasks due to laziness, leaving {len(tasks)}")

    tasks_finished, tasks_failed, tasks_timed_out, tasks_skipped = run_all_tasks(tasks, workers, dryrun)

    end_time = datetime.datetime.now()
    print(f"Done in {end_time - start_time}")

    # If we timed out on or skipped some tasks, list them at the end and return status code 1
    if len(tasks_failed) != 0:
        print(f"WARNING: {len(tasks_failed)} tasks failed:")
        for task in tasks_failed:
            print(f"  ({task.index}) {task.name}")

    # If we timed out on or skipped some tasks, list them at the end and return status code 1
    if len(tasks_timed_out) != 0:
        print(f"WARNING: {len(tasks_timed_out)} tasks timed out:")
        for task in tasks_timed_out:
            print(f"  ({task.index}) {task.name}")

    if len(tasks_skipped) != 0:
        print(f"WARNING: and {len(tasks_skipped)} tasks were skipped due to depending on failed or timed out tasks:")
        for task in tasks_skipped:
            print(f"  ({task.index}) {task.name}")

    # Return true if all tasks were successful
    return len(tasks_finished) == len(tasks)


def run_validation(benchmarks, dryrun=False):
    # Run at most one script at a time, in case we want to do timing at some point
    print("==== Executing validation scripts ====")
    start_time = datetime.datetime.now()

    for bench in benchmarks:
        if bench.validator is None:
            continue

        linked_binary = os.path.abspath(bench.clang_link_output)
        if not os.path.exists(linked_binary):
            print(f"Missing binary for validation: {linked_binary}")
            return False

        if dryrun:
            print(f"(dryrun) Validating {bench.name}")
            continue
        else:
            print(f"Validating {bench.name}")

        try:
            validator_dir = os.path.dirname(bench.validator)
            validator_script = "./" + os.path.basename(bench.validator)
            result = run_command([validator_script, linked_binary], cwd=validator_dir)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return False

    end_time = datetime.datetime.now()
    print(f"==== All validation scripts passed in {end_time - start_time}! ====")
    return True


def intOrNone(value):
    return int(value) if value is not None else None


def main():
    parser = argparse.ArgumentParser(description='Compile benchmarks using jlm-opt')
    parser.add_argument('--llvmbin', dest='llvm_bindir', action='store', required=True,
                        help='Specify bindir of LLVM tools and clang. [Required]')
    parser.add_argument('--jlm-opt', dest='jlm_opt', action='store', required=True,
                        help=f'Specify the jlm-opt binary used. [Required]')
    parser.add_argument('--sources', dest='sources_file', action='store', required=True,
                        help=f'Specify the sources.json file containing benchmark descriptions. [Required]')
    parser.add_argument('--builddir', dest='build_dir', action='store', default=Options.DEFAULT_BUILD_DIR,
                        help=f'Specify the build folder to build benchmarks in. [{Options.DEFAULT_BUILD_DIR}]')
    parser.add_argument('--statsdir', dest='stats_dir', action='store', default=Options.DEFAULT_STATS_DIR,
                        help=f'Specify the folder to put jlm-opt statistics in. [{Options.DEFAULT_STATS_DIR}]')
    parser.add_argument('--jlmV', dest='jlm_opt_verbosity', action='store', default=Options.DEFAULT_JLM_OPT_VERBOSITY,
                        help=f'Set verbosity level for jlm-opt. [{Options.DEFAULT_JLM_OPT_VERBOSITY}]')

    parser.add_argument('--full-spec', dest='full_spec', action='store_true',
                        help='Use the full cpu2017, instead of the redistributable sources')
    parser.add_argument('--filter', metavar='FILTER', dest='filters', action='append', default=None,
                        help=('Only run benchmarks if the name contains a match for the given regex. ' +
                              'If multiple filters are specified, the union of their matches is used.'))
    parser.add_argument('--list', dest='list_benchmarks', action='store_true',
                        help='List (filtered) benchmarks and exit')

    parser.add_argument('--offset', metavar='O', dest='offset', action='store', default="0",
                        help='Skip the first O tasks. [0]')
    parser.add_argument('--limit', metavar='L', dest='limit', action='store', default=None,
                        help='Execute at most L tasks. [infinity]')
    parser.add_argument('--stride', metavar='S', dest='stride', action='store', default="1",
                        help='Executes every S task, starting at offset [1]')
    parser.add_argument('--eager', dest='eager', action='store_true',
                        help='Makes tasks run even if all their outputs exist')
    parser.add_argument('--dry-run', dest='dryrun', action='store_true',
                        help='Prints the name of each task that would run, but does not run it')
    parser.add_argument('--timeout', dest='timeout', action='store', default=None,
                        help='Sets a maximum allowed runtime for subprocesses. In seconds. The process may run for at most a minute longer.')

    parser.add_argument('-j', metavar='N', dest='workers', action='store', default='1',
                        help='Run up to N tasks in parallel when possible')

    parser.add_argument('--do-validation', dest='do_validation', action='store_true',
                        help='Run validation scripts after compiling and linking')

    parser.add_argument('--agnosticModRef', action='store_true', dest='agnosticModRef',
                        help='Uses agnostic memory state encoding')
    parser.add_argument('--regionAwareModRef', action='store_true', dest='regionAwareModRef',
                        help='Uses region aware memory state encoding')
    parser.add_argument('--useMem2reg', action='store_true', dest='useMem2reg',
                        help='Uses LLVM opt\'s mem2reg pass')


    args = parser.parse_args()

    global options
    options = Options(llvm_bindir=args.llvm_bindir,
                      build_dir=args.build_dir,
                      stats_dir=args.stats_dir,
                      jlm_opt=args.jlm_opt,
                      jlm_opt_verbosity=int(args.jlm_opt_verbosity),
                      timeout=intOrNone(args.timeout))

    dryrun = args.dryrun
    if not dryrun:
        ensure_folder_exists(options.get_build_dir())
        ensure_folder_exists(options.get_stats_dir())

    def should_keep_benchmark(benchmark):
        # Ensure that either cpu2017 or redist2017 are being used, not both
        if benchmark.name.startswith("cpu2017-") and not args.full_spec:
            return False
        if benchmark.name.startswith("redist2017-") and args.full_spec:
            return False

        if args.filters:
            return any(re.search(filt, benchmark.name) for filt in args.filters)

        return True

    benchmarks = get_benchmarks(args.sources_file)
    benchmarks = [bench for bench in benchmarks if should_keep_benchmark(bench)]
    
    if args.list_benchmarks:
        print(f"{len(benchmarks)} benchmarks:")
        for bench in benchmarks:
            print(f"  {bench.name:<20} {len(bench.cfiles):4d} C files")
        sys.exit(0)

    offset = int(args.offset)
    stride = int(args.stride)
    limit = float("inf")
    if args.limit is not None:
        limit = int(args.limit)
    eager = args.eager
    workers = int(args.workers)
    if dryrun: # There is no point in multithreading the dryruns
        workers = 1

    env_vars = {}
    for bench in benchmarks:
        configure_benchmark(bench, args)

    # Perform all compilation and linking tasks
    success = run_benchmarks(benchmarks,
                             env_vars=env_vars,
                             offset=offset,
                             limit=limit,
                             stride=stride,
                             eager=eager,
                             workers=workers,
                             dryrun=dryrun)
    if not success:
        return 1

    # If all tasks finished sucessfully and validation is requested, perform it
    if args.do_validation:
        success = run_validation(benchmarks,
                                 dryrun=dryrun)
        if not success:
            return 1

    return 0


def configure_benchmark(bench, args):
    """
    Called by the main() function on each benchmark to do run customization
    """

    # The top one leads to no tbaa info, while the bottom one includes it
    bench.extra_clang_flags = ["-Xclang", "-disable-O0-optnone"]
    # bench.extra_clang_flags = ["-O2", "-Xclang", "-disable-llvm-passes"]

    if args.useMem2reg:
        bench.opt_flags = ["-passes=mem2reg"]

    # Configure the flags sent to jlm-opt here
    bench.jlm_opt_flags = ["--print-andersen-analysis", "--print-store-value-forwarding", "--print-rvsdg-construction", "--print-rvsdg-destruction", "--print-rvsdg-optimization"]
    bench.jlm_opt_flags.append("--annotations=NumMemoryStateInputsOutputs,NumLoadNodes,NumStoreNodes,NumAllocaNodes")# , "--print-aa-precision-evaluation"]

    bench.jlm_opt_flags.append("--RvsdgTreePrinter")

    bench.jlm_opt_flags.extend(["--FunctionInlining", "--PredicateCorrelation",
                                #"--LoopUnswitching",
                                "--CommonNodeElimination", "--InvariantValueRedirection", "--DeadNodeElimination"])

    bench.jlm_opt_flags.append("--RvsdgTreePrinter")

    if args.agnosticModRef:
        bench.jlm_opt_flags.extend(["--AAAndersenAgnostic", "--print-agnostic-mod-ref-summarization", "--print-basicencoder-encoding"])

    if args.regionAwareModRef:
        bench.jlm_opt_flags.extend(["--AAAndersenRegionAware", "--print-mod-ref-summarization", "--print-basicencoder-encoding"])

    bench.jlm_opt_flags.append("--RvsdgTreePrinter")

    bench.jlm_opt_flags.append("--StoreValueForwarding")

    bench.jlm_opt_flags.append("--RvsdgTreePrinter")

    bench.jlm_opt_flags.extend(["--LoadChainSeparation", "--CommonNodeElimination", "--InvariantValueRedirection", "--NodeReduction", "--DeadNodeElimination"])

    bench.jlm_opt_flags.append("--RvsdgTreePrinter")

    # Uncomment to disable linking
    # bench.clang_link_output = None

    # Uncomment to disable all use of jlm-opt
    # bench.jlm_opt_flags = []


if __name__ == "__main__":
    returncode = main()
    sys.exit(returncode)
