"""
This file is the main script for running SCALE-Sim with the given topology and configuration files.
It handles argument parsing and execution.
"""
from scalesim.report_utils import prepare_output_dir, postprocess_reports

import argparse

from scalesim.scale_sim import scalesim

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', metavar='Topology file', type=str,
                        default="./topologies/conv_nets/test.csv",
                        help="Path to the topology file"
                        )
    parser.add_argument('-l', metavar='Layout file', type=str,
                        default="./layouts/conv_nets/test.csv",
                        help="Path to the layout file"
                        )
    parser.add_argument('-c', metavar='Config file', type=str,
                        default="./configs/scale.cfg",
                        help="Path to the config file"
                        )
    parser.add_argument('-p', metavar='log dir', type=str,
                        default="./results/",
                        help="Path to log dir"
                        )
    parser.add_argument('-i', metavar='input type', type=str, default="conv", choices=['conv', 'gemm'],
                        help="Type of input topology, gemm: MNK, conv: conv")
    parser.add_argument('-s', metavar='save trace', type=str.upper, default="Y", choices=['Y', 'N'],
                        help="Save Trace: (Y/N)")

    parser.add_argument('--save-trace', dest='save_trace_flag', action='store_true',
                        help='Save detailed per-layer trace CSV files')
    parser.add_argument('--no-save-trace', dest='save_trace_flag', action='store_false',
                        help='Do not save detailed per-layer trace CSV files; only write reports')
    parser.set_defaults(save_trace_flag=None)
    parser.add_argument('--overwrite-output', action='store_true',
                        help='Allow writing into an existing output directory')
    parser.add_argument('--unique-output-dir', action='store_true',
                        help='If output directory exists, create a timestamped sibling directory')
    parser.add_argument('--quiet', action='store_true',
                        help='Suppress per-layer progress and summary output')
    args = parser.parse_args()
    topology = args.t
    layout = args.l
    config = args.c
    logpath = args.p
    requested_logpath = logpath
    verbose = not args.quiet
    logpath = prepare_output_dir(
        logpath,
        overwrite=args.overwrite_output,
        unique=args.unique_output_dir,
        verbose=verbose,
    )
    inp_type = args.i
    if args.save_trace_flag is not None:
        save_trace_enabled = bool(args.save_trace_flag)
    else:
        save_trace_enabled = (args.s == 'Y')

    GEMM_INPUT = False
    if inp_type.lower() == 'gemm':
        GEMM_INPUT = True
    # scalesim(save_disk_space=True) means do NOT save layer traces.
    save_space = not save_trace_enabled

    s = scalesim(save_disk_space=save_space,
                 verbose=verbose,
                 config=config,
                 topology=topology,
                 layout=layout,
                 input_type_gemm=GEMM_INPUT
                 )
    s.run_scale(top_path=logpath)

    # The simulator writes reports into <logpath>/<run_name>. Post-process that actual directory,
    # not the parent requested directory. This keeps CSV cleanup, metadata, and summary in sync.
    actual_report_dir = getattr(getattr(s, 'runner', None), 'top_path', logpath)
    postprocess_reports(
        actual_report_dir,
        args=args,
        requested_output=requested_logpath,
        save_traces=save_trace_enabled,
        scale_obj=s,
        verbose=verbose,
    )
