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
    DEFAULT_LLVM_BINDIR = "/usr/local/lib/llvm18/bin/"
    DEFAULT_SOURCES = "sources/sources.json"
    DEFAULT_BUILD_DIR = "build/default/"
    DEFAULT_STATS_DIR = "statistics/default/"
    DEFAULT_JLM_OPT = "../jlm/build-release/jlm-opt"
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

def run_command_and_capture(command, env_vars=None):
    p = subprocess.run(command, env=env_vars, capture_output=True, text=True, check=True)
    return p.stdout, p.stderr

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


class Task:
    def __init__(self, *, name, input_files, output_files, action, skip_if_any_file_exists=None):
        self.name = name
        self.input_files = input_files
        self.output_files = output_files
        self.action = action

        # Bonus list of files that can cause this task to be skipped
        self.skip_if_any_file_exists = [] if skip_if_any_file_exists is None else skip_if_any_file_exists

    def run(self):
        self.action(self)

def any_output_matches(task, regex):
    """Returns true if any one of the output files of the given task contains a match for the given regex"""
    return any(regex.search(of) is not None for of in task.output_files)

def can_skip_task(task):
    """
    Returns true if all outputs of the given task already exist.
    Or the disk has a file that allows the task to be skipped.
    """
    all_outputs_exist = all(os.path.exists(of) for of in task.output_files)

    if all_outputs_exist:
        return True

    for skip_if_exists in task.skip_if_any_file_exists:
        if os.path.isfile(skip_if_exists):
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


def compile_file(tasks, full_name, workdir, cfile, extra_clang_flags, stats_dir,
                 env_vars=None, opt_flags=None, jlm_opt_flags=None, jlm_opt_suffix=None):
    """
    Compiles the given file with the given arguments to clang.
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

def link_and_optimize(tasks, full_name, compiled_cfiles, compiled_non_cfiles, stats_dir,
                      env_vars=None, llvm_link_flags=None, opt_flags=None, jlm_opt_flags=None, clang_link_flags=None):
    """
    Links together the given files. The files can be LLVM IR files or object files.
    opt and jlm-opt can only be used if llvm-link is enabled.
    If llvm-link is not enabled, the final clang command will be given all the input files.

    :param tasks: the list of tasks to append commands to
    :param full_name: should be a valid filename, unique to the program
    :param compiled_cfiles: a list of LLVM IR/bitcode files, relative to CWD
    :param compiled_non_cfiles: a list of object files, relative to CWD
    :param stats_dir: the directory to place statistics files in
    :param env_vars: environment variables passed to the executed commands
    :param llvm_link_flags: if not None, llvm-link is run with the given flags
    :param opt_flags: if not None, opt is run with the given flags
    :param jlm_opt_flags: if not None, jlm-opt is run with the given flags
    :param clang_link_flags: if not None, clang is used to create a binary
    :return: a tuple with paths to (llvm-link's output, opt's output, jlm-opt's output, clang's final output)
    """
    assert "/" not in full_name

    llvm_link_out = options.get_build_dir(f"{full_name}-llvm-link-out.ll")
    opt_out = options.get_build_dir(f"{full_name}-opt-out.ll")
    jlm_opt_out = options.get_build_dir(f"{full_name}-jlm-opt-out.ll")
    clang_link_out = options.get_build_dir(f"{full_name}-clang-link-out")

    combined_env_vars = os.environ.copy()
    if env_vars is not None:
        combined_env_vars.update(env_vars)

    if llvm_link_flags is not None:
        llvm_link_command = [options.llvm_link, "-S",
                             *compiled_cfiles, "-o", llvm_link_out, *llvm_link_flags]
        tasks.append(Task(name=f"llvm-link {full_name}",
                          input_files=compiled_cfiles,
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

        compiled_cfiles = [jlm_opt_out]
    else:
        # Without llvm-link, opt and jlm-opt can not be used
        assert opt_flags is None and jlm_opt_flags is None

    if clang_link_flags is not None:
        clang_command = [options.clang_link, *compiled_cfiles, *compiled_non_cfiles, "-o", clang_link_out, *clang_link_flags]
        tasks.append(Task(name=f"clang (link) {full_name}",
                          input_files=compiled_cfiles,
                          output_files=[clang_link_out],
                          action=lambda task: run_command(clang_command, env_vars=combined_env_vars, timeout=options.timeout)))

    return (llvm_link_out, opt_out, jlm_opt_out, clang_link_out)

def find_common_prefix(strings):
    prefix, *rest = strings
    for string in rest:
        while not string.startswith(prefix):
            prefix = prefix[:-1]
    return prefix

class CFile:
    def __init__(self, working_dir, cfile, ofile, arguments):
        """
        :param working_dir: the folder from which to compile, relative to CWD
        :param cfile: the C file to compile, relative to working_dir
        :param ofile: the ofile originally produced by this command, relative to CWD
        :param arguments: flags to pass to the compiler
        """
        self.working_dir = working_dir
        self.cfile = cfile
        self.ofile = ofile
        self.arguments = arguments

    def get_abspath(self):
        return os.path.abspath(os.path.join(self.working_dir, self.cfile))

class Benchmark:
    def __init__(self, name, cfiles, ofiles, linker_arguments):
        """
        Constructs a benchmark representing a single program.
        The input passed to this constructor represents the "standard" compile+link pipeline.
        This can be customized by modifying the fields on the constructed class.

        If any cfile produces one of the ofiles needed for linking, the produced ofile is used instead.
        This is why all ofiles need to be listed relative to CWD.

        :param name: the name of the program
        :param cfiles: a list of instances of CFile
        :param ofiles: the list of object files to be linked, relative to CWD
        :param linker_arguments: list of linker flags, or None to disable linking
        """
        self.name = name
        self.cfiles = cfiles
        self.ofiles = ofiles

        # Avoid including parts of the source paths that are shared between all cfiles in the program
        self.common_abspath = find_common_prefix(cfile.get_abspath() for cfile in self.cfiles)

        # Per C-file compilation and optimization flags
        self.extra_clang_flags = []
        self.opt_flags = None
        self.jlm_opt_flags = None

        # Whole program optimization and linking flags
        self.llvm_link_flags = None
        self.linked_opt_flags = None
        self.linked_jlm_opt_flags = None
        self.clang_link_flags = linker_arguments

        # Add an optional suffix to outputs of jlm-opt
        self.jlm_opt_suffix = None

        self.jlm_opt_allowlist = None

    def get_full_cfile_name(self, cfile):
        """Get a cfile name, including the program name, and enough of the path to make it unique"""
        abspath = cfile.get_abspath()
        assert abspath.startswith(self.common_abspath)
        path = abspath[len(self.common_abspath):]
        return f"{self.name}+{path}".replace("/", "_")

    def get_tasks(self, stats_dir, env_vars):
        tasks = []

        # Maps from the ofile name used in sources, to the output file produced by jlm-opt
        ofile_mapping = {}

        for i, cfile in enumerate(self.cfiles):
            full_name = self.get_full_cfile_name(cfile)

            # TODO: RAM skip
            if "makesrna_intern_rna_nodetree_gen.c" in full_name:
                continue

            # Skipping running jlm-opt if there is an allowlist and we are not on it
            jlm_opt_flags = self.jlm_opt_flags
            if self.jlm_opt_allowlist is not None and i not in self.jlm_opt_allowlist:
                jlm_opt_flags = None

            _, _, outfile = compile_file(tasks, full_name=full_name, workdir=cfile.working_dir, cfile=cfile.cfile,
                                         stats_dir=stats_dir, env_vars=env_vars,
                                         extra_clang_flags=[*self.extra_clang_flags, *cfile.arguments],
                                         opt_flags=self.opt_flags,
                                         jlm_opt_flags=jlm_opt_flags,
                                         jlm_opt_suffix=self.jlm_opt_suffix)
            ofile_mapping[cfile.ofile] = outfile

        # Try as much as possible to use the LLVM IR files produced above when linking
        compiled_cfiles = []
        compiled_non_cfiles = []
        for ofile in self.ofiles:
            if ofile in ofile_mapping:
                compiled_cfiles.append(ofile_mapping[ofile])
            else:
                compiled_non_cfiles.append(ofile)

        link_and_optimize(tasks, full_name=self.name, compiled_cfiles=compiled_cfiles, compiled_non_cfiles=compiled_non_cfiles,
                          stats_dir=stats_dir, env_vars=env_vars,
                          llvm_link_flags=self.llvm_link_flags,
                          opt_flags=self.linked_opt_flags,
                          jlm_opt_flags=self.linked_jlm_opt_flags,
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
        cfiles = []
        for cfile_data in data["cfiles"]:
            working_dir = os.path.join(sources_folder, cfile_data["working_dir"])
            cfile = cfile_data["cfile"]
            ofile = os.path.join(sources_folder, cfile_data["ofile"])
            arguments = cfile_data["arguments"]
            cfiles.append(CFile(working_dir=working_dir, cfile=cfile, ofile=ofile, arguments=arguments))

        ofiles = []
        for ofile in data["ofiles"]:
            ofiles.append(os.path.join(sources_folder, ofile))

        linker_arguments = data["linker_arguments"]
        if len(ofiles) == 0:
            # Disable linking if we have not tracked linking properly
            linker_arguments = None

        benchmarks.append(Benchmark(name=name,
                                    cfiles=cfiles,
                                    ofiles=ofiles,
                                    linker_arguments=linker_arguments))

    # Sort benchmarks in order of ascending number of C files
    benchmarks.sort(key=lambda bench: len(bench.cfiles))

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

    # Only give return code 0 if all attempted tasks finished successfully
    return 0 if len(tasks_finished) == len(tasks) else 1

def intOrNone(value):
    return int(value) if value is not None else None


def main():
    parser = argparse.ArgumentParser(description='Compile benchmarks using jlm-opt')
    parser.add_argument('--llvmbin', dest='llvm_bindir', action='store', default=Options.DEFAULT_LLVM_BINDIR,
                        help='Specify bindir of LLVM tools and clang')
    parser.add_argument('--sources', dest='sources_file', action='store', default=Options.DEFAULT_SOURCES,
                        help=f'Specify the sources.json file to scan for benchmarks in [{Options.DEFAULT_SOURCES}]')
    parser.add_argument('--builddir', dest='build_dir', action='store', default=Options.DEFAULT_BUILD_DIR,
                        help=f'Specify the build folder to build benchmarks in. [{Options.DEFAULT_BUILD_DIR}]')
    parser.add_argument('--statsdir', dest='stats_dir', action='store', default=Options.DEFAULT_STATS_DIR,
                        help=f'Specify the folder to put jlm-opt statistics in. [{Options.DEFAULT_STATS_DIR}]')
    parser.add_argument('--jlm-opt', dest='jlm_opt', action='store', default=Options.DEFAULT_JLM_OPT,
                        help=f'Override the jlm-opt binary used. [{Options.DEFAULT_JLM_OPT}]')
    parser.add_argument('--jlmV', dest='jlm_opt_verbosity', action='store', default=Options.DEFAULT_JLM_OPT_VERBOSITY,
                        help=f'Set verbosity level for jlm-opt. [{Options.DEFAULT_JLM_OPT_VERBOSITY}]')

    parser.add_argument('--filter', metavar='FILTER', dest='benchmark_filter', action='store', default=None,
                        help='Only include benchmarks whose name includes a match of the given regex')
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
    parser.add_argument('--clean', dest='clean', action='store_true',
                        help='Remove the build and stats folders before running')

    parser.add_argument('--configSweepIterations', metavar='N', action='store', default=0, type=int,
                        help='The number of times each possible Andersen solver config should be tested. [0]')
    parser.add_argument('--exactConfiguration', metavar='K', action='store', dest='exact_configuration', default=None,
                        help='Picks exactly one configuration to use')

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
        if args.clean:
            shutil.rmtree(options.get_build_dir(), ignore_errors=True)
            shutil.rmtree(options.get_stats_dir(), ignore_errors=True)

        ensure_folder_exists(options.get_build_dir())
        ensure_folder_exists(options.get_stats_dir())

    benchmarks = get_benchmarks(args.sources_file)

    if args.benchmark_filter is not None:
        regex = re.compile(args.benchmark_filter)
        benchmarks = [bench for bench in benchmarks if regex.search(bench.name)]
    
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
    if args.configSweepIterations != 0:
        env_vars.update({
            "JLM_ANDERSEN_TEST_ALL_CONFIGS": str(args.configSweepIterations),
            "JLM_ANDERSEN_DOUBLE_CHECK": "YES"
        })
    if args.exact_configuration is not None:
        env_vars.update({
            "JLM_ANDERSEN_USE_EXACT_CONFIG": args.exact_configuration
        })

    for bench in benchmarks:
        # The top one leads to no tbaa info, while the bottom one includes it
        bench.extra_clang_flags = ["-Xclang", "-disable-O0-optnone"]
        # bench.extra_clang_flags = ["-O2", "-Xclang", "-disable-llvm-passes"]

        # Uncomment the below line to run opt on each LLVM IR file before passing it to jlm-opt
        # bench.opt_flags = ["--passes=mem2reg"]

        if args.useMem2reg:
            bench.opt_flags = ["-passes=mem2reg"]

        # Configure the flags sent to jlm-opt here
        bench.jlm_opt_flags = ["--print-andersen-analysis", "--print-store-value-forwarding", "--print-rvsdg-construction", "--print-rvsdg-destruction", "--print-rvsdg-optimization"]
        bench.jlm_opt_flags.append("--annotations=NumMemoryStateInputsOutputs,NumLoadNodes,NumStoreNodes,NumAllocaNodes")# , "--print-aa-precision-evaluation"]

        #bench.jlm_opt_flags.append("--RvsdgTreePrinter")

        bench.jlm_opt_flags.extend(["--FunctionInlining", "--PredicateCorrelation", "--LoopUnswitching", "--CommonNodeElimination", "--InvariantValueRedirection", "--DeadNodeElimination"])

        #bench.jlm_opt_flags.append("--RvsdgTreePrinter")

        if args.agnosticModRef:
            bench.jlm_opt_flags.extend(["--AAAndersenAgnostic", "--print-agnostic-mod-ref-summarization", "--print-basicencoder-encoding"])

        if args.regionAwareModRef or args.useMem2reg:
            bench.jlm_opt_flags.extend(["--AAAndersenRegionAware", "--print-mod-ref-summarization", "--print-basicencoder-encoding"])

        #bench.jlm_opt_flags.append("--RvsdgTreePrinter")

        bench.jlm_opt_flags.append("--StoreValueForwarding")

        #bench.jlm_opt_flags.append("--RvsdgTreePrinter")

        bench.jlm_opt_flags.extend(["--LoadChainSeparation", "--CommonNodeElimination", "--InvariantValueRedirection", "--NodeReduction", "--DeadNodeElimination"])

        #bench.jlm_opt_flags.append("--RvsdgTreePrinter")

        # Disable linking
        bench.clang_link_flags = None

    # If any tasks time out or fail, the script will have a non-zero return code
    return run_benchmarks(benchmarks,
                          env_vars=env_vars,
                          offset=offset,
                          limit=limit,
                          stride=stride,
                          eager=eager,
                          workers=workers,
                          dryrun=dryrun)

if __name__ == "__main__":
    returncode = main()
    sys.exit(returncode)
