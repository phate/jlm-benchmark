#!/usr/bin/env python3
import os
import os.path
import sys
import shutil
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
import re

def get_memory_node_counts(suffix):
    return [
        "#TotalAllocaState" + suffix,
        "#TotalMallocState" + suffix,
        "#TotalDeltaState" + suffix,
        "#TotalImportState" + suffix,
        "#TotalLambdaState" + suffix,
        "#TotalExternalState" + suffix,
        "#TotalNonEscapedState" + suffix,
        "#MaxMemoryState" + suffix,
        "#MaxNonEscapedMemoryState" + suffix,
        #"#TotalMemoryNodes" + suffix,
        #"#TotalIntervals" + suffix,
        #"#MaxIntervals" + suffix
    ]

def map_optimization_statistic(original_name):
    if original_name == "Time[ns]":
        return "OptimizationTime[ns]"
    elif original_name in ["#RvsdgNodesBefore", "#RvsdgNodesAfter"]:
        return original_name + "Sequence"

    return "TransformationPass-" + original_name

# For each statistic, this dict contains which values to keep
# If the entry is a tuple (name, rename), the statistic called `name` will be kept, but be called `rename`
# If the entry is a function, it takes the old name and provides the new name, or None to discard
METRICS_MAPPING = {
    "AndersenAnalysis": [
        "#RvsdgNodes",
        "#PointsToGraphAllocaNodes", "#PointsToGraphMallocNodes", "#PointsToGraphDeltaNodes", "#PointsToGraphImportNodes", "#PointsToGraphLambdaNodes",
        "#PointsToGraphMemoryNodes", "#PointsToGraphRegisterNodes", "#PointsToGraphEscapedNodes", "#PointsToGraphNodes", "#PointsToGraphEdges",
        ("AnalysisTimer[ns]", "AndersenAnalysisTimer[ns]"),
        ("SetAndConstraintBuildingTimer[ns]", "AndersenSetBuildingTimer[ns]"), ("OVSTimer[ns]", "AndersenOVSTimer[ns]"),
        ("ConstraintSolvingWorklistTimer[ns]", "AndersenWorklistTimer[ns]"), "PointsToGraphConstructionTimer[ns]",
    ],
    "RegionAwareModRefSummarizer": [
        "#SimpleAllocas",
        "#NonReentrantAllocas",
        "CallGraphTimer[ns]",
        "AllocasDeadInSccsTimer[ns]",
        "SimpleAllocasSetTimer[ns]",
        "NonReentrantAllocaSetsTimer[ns]",
        "CreateExternalModRefSetTimer[ns]", # Node
        "AnnotationTimer[ns]",
        "SolvingTimer[ns]",
        #"CreateMemoryNodeOrderingTimer[ns]",
        #"CreateModRefSummaryTimer[ns]",
    ],
    "MemoryStateEncoder": [
        "#IntraProceduralRegions",
        *get_memory_node_counts("Arguments"),
        "#LoadOperations",
        *get_memory_node_counts("sThroughLoad"),
        "#StoreOperations",
        *get_memory_node_counts("sThroughStore"),
        "#CallEntryMergeOperations",
        *get_memory_node_counts("sIntoCallEntryMerge"),
        "#ModRefSetOperations",
        "#TotalModRefSetIntervals",
        "#TotalLiveIntervals",
        ("Time[ns]", "MemoryStateEncodingTime[ns]")
    ],
    "InterProceduralGraphToRvsdg": [
        ("Time[ns]", "RvsdgConstructionTime[ns]")
    ],
    "StoreValueForwarding": [
        "#TotalLoads",
        "#LoadsForwarded",
        ("Time[ns]", "StoreValueForwardingTime[ns]")
    ],
    "RVSDGOPTIMIZATION": map_optimization_statistic,
    "RVSDGDESTRUCTION": [
        ("Time[ns]", "RvsdgDestructionTime[ns]")
    ]
}

def read_rvsdg_tree(path, prefix):
    data = {
        "NumAllocaNodes": 0,
        "NumStoreNodes": 0,
        "NumLoadNodes": 0,
        "NumMemoryStateTypeArguments": 0
    }
    with open(path, encoding='utf-8') as fd:
        for line in fd:
            if "Region" not in line:
                continue
            for part in line.split(" ")[1:]:
                stat, value = part.split(":")
                if stat in data:
                    data[stat] = data[stat] + int(value)

    return { f"{prefix}{key}": value for key, value in data.items() }

def get_metric_name(statistic, original_name):
    if statistic not in METRICS_MAPPING:
        return None

    mapping = METRICS_MAPPING[statistic]

    if callable(mapping):
        return mapping(original_name)

    for entry in mapping:
        if isinstance(entry, tuple):
            old, new = entry
            if original_name == old:
                return new
        elif original_name == entry:
            return entry

    return None

def extract_file_data(folder):
    file_datas = []

    files = os.listdir(folder)

    for fil in files:
        if not fil.endswith(".log"):
            continue

        file_data = {}
        cfile = fil[:-4]
        file_data["cfile"] = cfile

        with open(os.path.join(folder, fil), "r", encoding="utf-8") as fd:
            for line in fd:
                statistic, _, *parts = line.split(" ")

                for part in parts:
                    original_name, value = part.split(":")

                    metric_name = get_metric_name(statistic, original_name)
                    if not metric_name:
                        continue

                    try:
                        file_data[metric_name] = int(value)
                    except:
                        file_data[metric_name] = value

        for fil2 in files:
            if not fil2.startswith(cfile):
                continue
            if "rvsdgTree" not in fil2:
                continue

            num = fil2[:-4].split("-")[-1]
            file_data.update(read_rvsdg_tree(os.path.join(folder, fil2), f"Tree{num}-"))

        file_datas.append(file_data)

    return pd.DataFrame(file_datas)

def calculate_total_ramrs_time(file_data):
    file_data["RegionAwareModRefSummarizerTime[ns]"] = (
        file_data["CallGraphTimer[ns]"] +
        file_data["AllocasDeadInSccsTimer[ns]"] +
        file_data["SimpleAllocasSetTimer[ns]"] +
        file_data["NonReentrantAllocaSetsTimer[ns]"] +
        file_data["CreateExternalModRefSetTimer[ns]"] +
        file_data["AnnotationTimer[ns]"] +
        file_data["SolvingTimer[ns]"])

def make_file_data(folder, configuration):
    file_data = extract_file_data(folder)
    file_data["Configuration"] = configuration

    return file_data

def main():
    parser = argparse.ArgumentParser(description='Process raw statistics from the given folder.')
    parser.add_argument('--stats-in', dest='stats_in', action='store', default="statistics",
                        help='The folder where statistics files are located')
    parser.add_argument('--stats-out', dest='stats_out', action='store', default="statistics-out",
                        help='Folder where aggregated statistics should be placed')
    args = parser.parse_args()

    if not os.path.exists(args.stats_out):
        os.mkdir(args.stats_out)
    def stats_out(filename=""):
        return os.path.join(args.stats_out, filename)

    data = (
        make_file_data(os.path.join(args.stats_in, "ci"), "RegionAwareModRef"),
        #make_file_data(os.path.join(args.stats_in, "debug-raware"), "RegionAwareModRef"),
        ## make_file_data(os.path.join(args.stats_in, "raware"), "RegionAwareModRef"),
        #make_file_data(os.path.join(args.stats_in, "raware-no-tricks"), "RegionAwareModRef-NoTricks"),
        #make_file_data(os.path.join(args.stats_in, "raware-only-dead-alloca-blocklist"), "RegionAwareModRef-OnlyDeadAllocaBlocking"),
        #make_file_data(os.path.join(args.stats_in, "raware-only-non-reentrant-alloca-blocklist"), "RegionAwareModRef-OnlyNonReeentrantAllocaBlocking"),
        #make_file_data(os.path.join(args.stats_in, "raware-only-operation-size-blocking"), "RegionAwareModRef-OnlyOperationSizeBlocking"),
        #make_file_data(os.path.join(args.stats_in, "raware-only-constant-memory-blocking"), "RegionAwareModRef-OnlyConstantMemoryBlocking"),
        #make_file_data(os.path.join(args.stats_in, "agnostic"), "AgnosticModRef"),
        ## make_file_data(os.path.join(args.stats_in, "m2r"), "Mem2Reg")
    )
    file_data = pd.concat(data)

    calculate_total_ramrs_time(file_data)

    file_data["TotalTime[ns]"] = file_data["RvsdgConstructionTime[ns]"] + file_data["OptimizationTime[ns]"] + file_data["RvsdgDestructionTime[ns]"]

    def add_total_memory_state_column(suffix):
        file_data["#TotalMemoryState" + suffix] = (
            file_data["#TotalAllocaState" + suffix] +
            file_data["#TotalMallocState" + suffix] +
            file_data["#TotalDeltaState" + suffix] +
            file_data["#TotalImportState" + suffix] +
            file_data["#TotalLambdaState" + suffix] +
            file_data["#TotalExternalState" + suffix]
        )

    add_total_memory_state_column("Arguments")
    add_total_memory_state_column("sThroughLoad")
    add_total_memory_state_column("sThroughStore")
    add_total_memory_state_column("sIntoCallEntryMerge")


    file_data.to_csv(stats_out("memstate-file-data.csv"))

if __name__ == "__main__":
    main()
