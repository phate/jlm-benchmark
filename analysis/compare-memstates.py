#!/usr/bin/env python3
import argparse
import os
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import plotly.express as px

def extract_column(data, column, configuration):
    return data[data["Configuration"] == configuration].set_index("cfile")[column]

def plot_ratio_between_configs(file_data, column, conf, baseline_conf, savefig=None):
    data = pd.DataFrame({
        conf: extract_column(file_data, column, conf),
        baseline_conf: extract_column(file_data, column, baseline_conf)
    })
    data.sort_values(baseline_conf, ascending=True, inplace=True)

    plt.figure(figsize=(7,3))

    data["ratio"] = data[conf] / data[baseline_conf]
    sns.scatterplot(x=range(len(data)), y=data["ratio"])

    plt.title(column, fontsize=10)
    plt.ylabel(f"{conf} / {baseline_conf}", fontsize=7)
    plt.xlabel(f"Files sorted by {baseline_conf}", fontsize=7)

    def xline(i):
        plt.gca().axvline(i, linewidth=1, zorder=3, color='#444')
        text = f"{data[baseline_conf].iloc[i]}"
        plt.gca().text(i, 0.1, s=text)

    for p in range(100, len(data), 100):
        xline(p)

    plt.tight_layout(pad=0.2)

    if savefig is not None:
        plt.savefig(savefig)
    else:
        plt.show()

def plot_ratio_between_columns(file_data, configuration, column, baseline_column, savefig=None):
    data = pd.DataFrame({
        column: extract_column(file_data, column, configuration),
        baseline_column: extract_column(file_data, baseline_column, configuration)
    })
    data.sort_values(baseline_column, ascending=True, inplace=True)

    plt.figure(figsize=(7,3))

    data["ratio"] = data[column] / data[baseline_column]
    sns.scatterplot(x=range(len(data)), y=data["ratio"])

    plt.title(configuration, fontsize=10)
    plt.ylabel(f"{column} / {baseline_column}", fontsize=7)
    plt.xlabel(f"Files sorted by {baseline_column}", fontsize=7)

    def xline(i):
        plt.gca().axvline(i, linewidth=1, zorder=3, color='#444')
        text = f"{data[baseline_column].iloc[i]}"
        plt.gca().text(i, 0.1, s=text)

    for p in range(100, len(data), 100):
        xline(p)

    plt.tight_layout(pad=0.2)

    if savefig is not None:
        plt.savefig(savefig)
    else:
        plt.show()

    # print(data.iloc[-10::]["ratio"])

def plot_column(file_data, configuration, column, savefig=None):
    data = pd.DataFrame({
        column: extract_column(file_data, column, configuration)
    })
    data.sort_values(column, ascending=True, inplace=True)

    plt.figure(figsize=(7,3))

    sns.scatterplot(x=range(len(data)), y=data[column])

    plt.title(configuration)
    plt.ylabel(f"{column}")
    plt.xlabel(f"Files sorted by {column}")

    def xline(i):
        plt.gca().axvline(i, linewidth=1, zorder=3, color='#444')
        text = f"{data[column].iloc[i]}"
        plt.gca().text(i, 0.1, s=text)

    for p in range(100, len(data), 100):
        xline(p)

    plt.tight_layout(pad=0.2)

    if savefig is not None:
        plt.savefig(savefig)
    else:
        plt.show()

    # print(data.iloc[-10::]["ratio"])

def plot_scatter(file_data, configuration, x_axis, y_axis, savefig=None, plotly=False):
    data = file_data[file_data["Configuration"] == configuration]

    if plotly:
        fig = px.scatter(data, x=x_axis, y=y_axis, title=configuration, hover_data=['cfile'])
        fig.show()
        return

    plt.figure(figsize=(7,3))

    sns.scatterplot(data, x=x_axis, y=y_axis)

    plt.title(configuration)
    plt.xlabel(x_axis)
    plt.ylabel(y_axis)

    plt.tight_layout(pad=0.2)

    if savefig is not None:
        plt.savefig(savefig)
    else:
        plt.show()

def plot_scatter_between_configs(file_data, column, x_axis, y_axis, savefig=None, plotly=False):
    data_x = file_data[file_data["Configuration"] == x_axis].set_index("cfile")[column]
    data_y = file_data[file_data["Configuration"] == y_axis].set_index("cfile")[column]

    data = pd.DataFrame({x_axis: data_x, y_axis: data_y}).reset_index()

    if plotly:
        fig = px.scatter(data, x=x_axis, y=y_axis, title=column, hover_data=['cfile'])
        fig.show()
        return

    plt.figure(figsize=(7,3))

    sns.scatterplot(data, x=x_axis, y=y_axis)

    plt.title(column)
    plt.xlabel(x_axis)
    plt.xlabel(y_axis)

    plt.tight_layout(pad=0.2)

    if savefig is not None:
        plt.savefig(savefig)
    else:
        plt.show()

def print_table(data, name="", number_fmt="{:.0f}"):
    """
    Pretty prints the given pandas DataFrame
    """

    # row major
    cells = [[""] + ["" for _ in data.columns] for _ in range(len(data) + 1)]
    cells[0][0] = name

    for j, column in enumerate(data.columns):
        cells[0][j + 1] = column

    for i, index in enumerate(data.index):
        cells[i + 1][0] = index

        for j, column in enumerate(data.columns):
            cells[i + 1][j + 1] = data.loc[index, column]

    # Find the length of the longest cell in each column
    max_column_width = [0 for _ in cells[0]]
    for i, row in enumerate(cells):
        for j, val in enumerate(row):

            if isinstance(val, str):
                val_len = len(val)
            else:
                val_len = len(number_fmt.format(val))

            max_column_width[j] = max(max_column_width[j], val_len)

    START = "| "
    HSTART = "+-"

    END = " |\n"
    HEND = "-+\n"

    VBAR = " | "
    HVBAR = "-+-"
    HBAR = "-"

    # Now print the whole thing

    result = []
    def out(text):
        result.append(text)

    def print_hline():
        out(HSTART)
        for j, column_width in enumerate(max_column_width):
            if j != 0:
                out(HVBAR)
            out(HBAR * column_width)
        out(HEND)

    print_hline()
    for i, row in enumerate(cells):
        if i == 1:
            print_hline()
        out(START)
        for j, val in enumerate(row):
            if j != 0:
                out(VBAR)
            if isinstance(val, str):
                out(val + " " * (max_column_width[j] - len(val)))
            else:
                val = number_fmt.format(val).replace(",", " ")
                out(" " * (max_column_width[j] - len(val)) + val)
        out(END)
    print_hline()

    print("".join(result))

def table_quartiles_per_configuration(file_data, configurations, column, fmt="{:,.0f}"):
    df = pd.DataFrame(columns=["p25", "p50", "p75", "p90", "p99", "max", "mean"])

    for configuration in configurations:
        data = extract_column(file_data, column, configuration)
        df.loc[configuration, "p25"] = data.quantile(q=0.25)
        df.loc[configuration, "p50"] = data.quantile(q=0.50)
        df.loc[configuration, "p75"] = data.quantile(q=0.75)
        df.loc[configuration, "p90"] = data.quantile(q=0.90)
        df.loc[configuration, "p99"] = data.quantile(q=0.99)
        df.loc[configuration, "max"] = data.max()
        df.loc[configuration, "mean"] = data.mean()

    print_table(df, name=column, number_fmt=fmt)
    return df

def table_quartiles_per_column(file_data, configuration, columns, fmt="{:,.0f}"):
    df = pd.DataFrame(columns=["p25", "p50", "p75", "p90", "p99", "max", "mean"])

    for column in columns:
        data = extract_column(file_data, column, configuration)
        df.loc[column, "p25"] = data.quantile(q=0.25)
        df.loc[column, "p50"] = data.quantile(q=0.50)
        df.loc[column, "p75"] = data.quantile(q=0.75)
        df.loc[column, "p90"] = data.quantile(q=0.90)
        df.loc[column, "p99"] = data.quantile(q=0.99)
        df.loc[column, "max"] = data.max()
        df.loc[column, "mean"] = data.mean()

    print_table(df, name=configuration, number_fmt=fmt)
    return df

def less_equal_more(file_data, config1, col1, config2, col2):
    data1 = file_data.loc[file_data["Configuration"]==config1, :].set_index("cfile").loc[:, col1]
    data2 = file_data.loc[file_data["Configuration"]==config2, :].set_index("cfile").loc[:, col2]

    less = data1 < data2
    less = set(less.index[less])

    equal = data1 == data2
    equal = set(equal.index[equal].values)

    more = data1 > data2
    more = set(more.index[more].values)

    return less, equal, more

def print_less_equal_more(name, less, equal, more):
    print(f"Less / Equal / More for: {name}")
    total = len(less | equal | more)
    print(f"Less  ({len(less):3}/{total}):", ', '.join(map(str, list(less)[:3])))
    print(f"Equal ({len(equal):3}/{total}):", ', '.join(map(str, list(equal)[:3])))
    print(f"More  ({len(more):3}/{total}):", ', '.join(map(str, list(more)[:3])))
    print()


def main():
    parser = argparse.ArgumentParser(description='Create results from from aggregated statistics.')
    parser.add_argument('--stats', dest='stats', action='store', default="statistics-out",
                        help='The folder where aggregated statistics are located')
    parser.add_argument('--out', dest='out', action='store', default="results",
                        help='Folder where result plots and tables should be placed')
    parser.add_argument('--plotly', action='store_true',
                        help='Use plotly to render interactive')
    args = parser.parse_args()

    plotly = args.plotly
    file_data = pd.read_csv(os.path.join(args.stats, "memstate-file-data.csv"))

    def result(filename=""):
        return os.path.join(args.out, filename)

    # Remove all files that are not present in all configurations
    nconfigs = file_data["Configuration"].nunique()
    keep_cfiles = file_data.groupby("cfile")["Configuration"].nunique() == nconfigs
    delete_cfiles = keep_cfiles[~keep_cfiles].index
    if len(delete_cfiles):
        print("Ingoring cfiles due to missing some configurations:", delete_cfiles)
    file_data = file_data[file_data["cfile"].map(keep_cfiles)]

    raware_configurations = ["RegionAwareModRef",
                             "RegionAwareModRef-OnlyDeadAllocaBlocking",
                             "RegionAwareModRef-OnlyNonReeentrantAllocaBlocking",
                             "RegionAwareModRef-OnlyOperationSizeBlocking",
                             "RegionAwareModRef-OnlyConstantMemoryBlocking",
                             "RegionAwareModRef-NoTricks"]
    #passes = [
    #    "RvsdgConstructionTime[us]",
    #    "RvsdgDestructionTime[us]",
    #]

    #table_quartiles_per_column(file_data, "RegionAwareModRef", passes)

    raware_steps = [
        "CallGraphTimer[ns]",
        "AllocasDeadInSccsTimer[ns]",
        "SimpleAllocasSetTimer[ns]",
        "NonReentrantAllocaSetsTimer[ns]",
        "CreateExternalModRefSetTimer[ns]",
        "AnnotationTimer[ns]",
        "SolvingTimer[ns]",
        ]
    table_quartiles_per_column(file_data, "RegionAwareModRef", raware_steps)

    andersen_steps = ["AndersenSetBuildingTimer[ns]", "AndersenOVSTimer[ns]", "AndersenWorklistTimer[ns]", "PointsToGraphConstructionTimer[ns]", "AndersenAnalysisTimer[ns]"]
    table_quartiles_per_column(file_data, "RegionAwareModRef", andersen_steps)

    #plot_scatter(file_data, "RegionAwareModRef", x_axis="#RvsdgNodes", y_axis="RegionAwareModRefSummarizerTime[us]", savefig=result("rawmr-time-vs-size.pdf"), plotly=plotly)
    #plot_scatter(file_data, "RegionAwareModRef", x_axis="#RvsdgNodes", y_axis="MemoryStateEncodingTime[us]", savefig=result("mse-time-vs-size.pdf"), plotly=plotly)

    #plot_scatter(file_data, "RegionAwareModRef", x_axis="#RvsdgNodesBeforeSequence", y_axis="#RvsdgNodesAfterSequence", savefig=result("size-before-vs-after.pdf"), plotly=plotly)

    # Time it takes to make Non reentrant alloca sets, against size of PtG
    # plot_scatter(file_data, "RegionAwareModRef", x_axis="#PointsToGraphEdges", y_axis="NonReentrantAllocaSetsTimer[ns]", plotly=True)
    # plot_scatter(file_data, "RegionAwareModRef", x_axis="#PointsToGraphAllocaNodes", y_axis="NonReentrantAllocaSetsTimer[ns]", plotly=True)
    # plot_scatter(file_data, "RegionAwareModRef", x_axis="#NonReentrantAllocas", y_axis="NonReentrantAllocaSetsTimer[ns]", plotly=True)

    #file_data["#RelevantOperations"] = file_data["#IntraProceduralRegions"] + file_data["#LoadOperations"] + file_data["#StoreOperations"] + file_data["#CallEntryMergeOperations"]
    #for step in ramrs_steps:
    #    plot_scatter(file_data, "RegionAwareModRef", x_axis="#RelevantOperations", y_axis=step, plotly=True)

    table_quartiles_per_configuration(file_data, raware_configurations, "MemoryStateEncodingTime[ns]")
    table_quartiles_per_configuration(file_data, raware_configurations, "RegionAwareModRefSummarizerTime[ns]")
    table_quartiles_per_configuration(file_data, raware_configurations, "StoreValueForwardingTime[ns]")

    print()

    #table_quartiles_per_configuration(file_data, raware_configurations, "#TotalMemoryStateArguments")
    #file_data["AverageMemoryStateArguments"] = file_data["#TotalMemoryStateArguments"] / file_data["#IntraProceduralRegions"]
    #table_quartiles_per_configuration(file_data, raware_configurations, "AverageMemoryStateArguments")

    #file_data["ReentrantAllocaRatio"] = 1 - file_data["#NonReentrantAllocas"] / file_data["#PointsToGraphAllocaNodes"]
    #table_quartiles_per_configuration(file_data, ["RegionAwareModRef", "Mem2Reg"], "ReentrantAllocaRatio", fmt="{:.4f}")

    print()

    table_quartiles_per_column(file_data, "RegionAwareModRef", ["Tree0-NumAllocaNodes", "Tree1-NumAllocaNodes", "Tree2-NumAllocaNodes", "Tree3-NumAllocaNodes", "Tree4-NumAllocaNodes"])
    table_quartiles_per_column(file_data, "RegionAwareModRef", ["Tree0-NumStoreNodes", "Tree1-NumStoreNodes", "Tree2-NumStoreNodes", "Tree3-NumStoreNodes", "Tree4-NumStoreNodes"])
    table_quartiles_per_column(file_data, "RegionAwareModRef", ["Tree0-NumLoadNodes", "Tree1-NumLoadNodes", "Tree2-NumLoadNodes", "Tree3-NumLoadNodes", "Tree4-NumLoadNodes"])

    table_quartiles_per_column(file_data, "Mem2Reg", ["Tree0-NumAllocaNodes", "Tree1-NumAllocaNodes", "Tree2-NumAllocaNodes", "Tree3-NumAllocaNodes"])
    table_quartiles_per_column(file_data, "Mem2Reg", ["Tree0-NumStoreNodes", "Tree1-NumStoreNodes", "Tree2-NumStoreNodes", "Tree3-NumStoreNodes"])
    table_quartiles_per_column(file_data, "Mem2Reg", ["Tree0-NumLoadNodes", "Tree1-NumLoadNodes", "Tree2-NumLoadNodes", "Tree3-NumLoadNodes"])

    print()

    print("Total number of files:", file_data["cfile"].nunique())

    less_loads, equal_loads, more_loads = less_equal_more(file_data, "RegionAwareModRef", "Tree4-NumLoadNodes", "Mem2Reg", "Tree0-NumLoadNodes")
    less_stores, equal_stores, more_stores = less_equal_more(file_data, "RegionAwareModRef", "Tree4-NumStoreNodes", "Mem2Reg", "Tree0-NumStoreNodes")
    less_allocas, equal_allocas, more_allocas = less_equal_more(file_data, "RegionAwareModRef", "Tree4-NumAllocaNodes", "Mem2Reg", "Tree0-NumAllocaNodes")

    print_less_equal_more("Loads", less_loads, equal_loads, more_loads)
    print_less_equal_more("Stores", less_stores, equal_stores, more_stores)
    print_less_equal_more("Allocas", less_allocas, equal_allocas, more_allocas)

    print_less_equal_more("AllThree", less_loads&less_stores&less_allocas, equal_loads&equal_stores&equal_allocas, more_loads&more_stores&more_allocas)

    raware_data = file_data[file_data["Configuration"]=="RegionAwareModRef"].set_index("cfile")
    print("File with more loads with fewest loads:", raware_data.loc[list(more_loads), "Tree4-NumLoadNodes"].idxmin())

    print()

    table_quartiles_per_column(file_data, "RegionAwareModRef", ["#TotalLoads", "#LoadsForwarded"])
    table_quartiles_per_column(file_data, "Mem2Reg", ["#TotalLoads", "#LoadsForwarded"])

    #table_quartiles_per_column(file_data, "AgnosticModRef", ["Tree0-NumAllocaNodes", "Tree1-NumAllocaNodes", "Tree2-NumAllocaNodes", "Tree3-NumAllocaNodes"])
    #table_quartiles_per_column(file_data, "AgnosticModRef", ["Tree0-NumStoreNodes", "Tree1-NumStoreNodes", "Tree2-NumStoreNodes", "Tree3-NumStoreNodes"])
    #table_quartiles_per_column(file_data, "AgnosticModRef", ["Tree0-NumLoadNodes", "Tree1-NumLoadNodes", "Tree2-NumLoadNodes", "Tree3-NumLoadNodes"])

    #table_quartiles_per_configuration(file_data, ["RegionAwareModRef", "Mem2Reg"], "#RvsdgNodes")

    # plot_ratio_between_configs(file_data, "#TotalMemoryStateArguments", "RegionAwareModRef", "RegionAwareModRef-Curtailed", savefig="results/memrefs-raware-vs-curtailed.pdf")

    #plot_ratio_between_configs(file_data, "#TotalMemoryStateArguments", "RegionAwareModRef-ExtraOpts", "RegionAwareModRef-New", savefig="results/memrefs-extraOpts-vs-new.pdf")
    #plot_ratio_between_configs(file_data, "#TotalLoads", "RegionAwareModRef-ExtraOpts", "RegionAwareModRef-New", savefig="results/memrefs-extraOpts-vs-new.pdf")
    #plot_ratio_between_configs(file_data, "#TotalStores", "RegionAwareModRef-ExtraOpts", "RegionAwareModRef-New", savefig="results/memrefs-extraOpts-vs-new.pdf")

    #plot_ratio_between_columns(file_data, "RegionAwareModRef", "#TotalDeltaStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-delta-ratio.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef", "#TotalAllocaStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-alloca-ratio.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef", "#TotalLambdaStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-lambda-ratio.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef", "#TotalImportStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-import-ratio.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef", "#TotalMallocStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-malloc-ratio.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef", "#TotalNonEscapedStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-nonescaped-ratio.pdf")

    #plot_ratio_between_columns(file_data, "RegionAwareModRef-Curtailed", "#TotalDeltaStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-delta-ratio-curtailed.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef-Curtailed", "#TotalAllocaStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-alloca-ratio-curtailed.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef-Curtailed", "#TotalLambdaStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-lambda-ratio-curtailed.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef-Curtailed", "#TotalImportStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-import-ratio-curtailed.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef-Curtailed", "#TotalMallocStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-malloc-ratio-curtailed.pdf")
    #plot_ratio_between_columns(file_data, "RegionAwareModRef-Curtailed", "#TotalNonEscapedStateArguments", "#TotalMemoryStateArguments", savefig="results/memstate-args-nonescaped-ratio-curtailed.pdf")

    #plot_column(file_data, "RegionAwareModRef-Curtailed", "#MaxMemoryStateArguments", savefig="results/memstate-args-max-curtailed.pdf")
    #plot_column(file_data, "RegionAwareModRef", "#MaxMemoryStateArguments", savefig="results/memstate-args-max-raware.pdf")
    #plot_column(file_data, "RegionAwareModRef", "#MaxNonEscapedMemoryStatesThroughLoad", savefig="results/memstate-loads-max-nonescaped.pdf")

if __name__ == "__main__":
    main()
