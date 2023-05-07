#===========================================================================================================
#------------------------------ GENERIC TECH DRC-malformed RULE DECK ---------------------------------------
#===========================================================================================================

"""
Run GENERIC TECH DRC-malformed runset.

Usage:
    run_drc.py (--help| -h)
    run_drc.py (--path=<file_path>) [--verbose] [--mp=<num_cores>] [--run_dir=<run_dir_path>] [--topcell=<topcell_name>] [--thr=<thr>] [--run_mode=<run_mode>] [--offgrid]

Options:
    --help -h                           Print this help message.
    --path=<file_path>                  The input GDS file path.
    --topcell=<topcell_name>            Topcell name to use.
    --mp=<num_cores>                    Run the rule deck in parts in parallel to speed up the run. [default: 1]
    --run_dir=<run_dir_path>            Run directory to save all the results [default: pwd]
    --thr=<thr>                         The number of threads used in run.
    --run_mode=<run_mode>               Select klayout mode Allowed modes (flat , deep, tiling). [default: deep]
    --verbose                           Detailed rule execution log for debugging.
"""

import glob
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from subprocess import check_call

import klayout.db
from docopt import docopt


def get_rules_with_violations(results_database):
    """
    This function will find all the rules that has violated in a database.

    Parameters
    ----------
    results_database : string or Path object
        Path string to the results file

    Returns
    -------
    set
        A set that contains all rules in the database with violations
    """

    mytree = ET.parse(results_database)
    myroot = mytree.getroot()

    all_violating_rules = set()

    for z in myroot[7]:  # myroot[7] : List rules with viloations
        all_violating_rules.add(f"{z[1].text}".replace("'", ""))

    return all_violating_rules


def check_drc_results(results_db_files: list):
    """
    check_drc_results Checks the results db generated from run and report at the end if the DRC run failed or passed.
    This function will exit with 1 if there are violations.

    Parameters
    ----------
    results_db_files : list
        A list of strings that represent paths to results databases of all the DRC runs.
    """

    if len(results_db_files) < 1:
        logging.error("Klayout did not generate any rdb results. Please check run logs")
        exit(1)

    full_violating_rules = set()

    for f in results_db_files:
        violating_rules = get_rules_with_violations(f)
        full_violating_rules.update(violating_rules)

    if len(full_violating_rules) > 0:
        logging.error("Klayout DRC run is not clean.")
        logging.error(f"Violated rules are : {str(full_violating_rules)}\n")
        exit(1)
    else:
        logging.info("Klayout DRC run is clean. GDS has no DRC violations.")


def get_top_cell_names(gds_path):
    """
    get_top_cell_names get the top cell names from the GDS file.

    Parameters
    ----------
    gds_path : string
        Path to the target GDS file.

    Returns
    -------
    List of string
        Names of the top cell in the layout.
    """
    layout = klayout.db.Layout()
    layout.read(gds_path)
    top_cells = [t.name for t in layout.top_cells()]

    return top_cells


def get_run_top_cell_name(arguments, layout_path):
    """
    get_run_top_cell_name Get the top cell name to use for running. If it's provided by the user, we use the user input.
    If not, we get it from the GDS file.

    Parameters
    ----------
    arguments : dict
        Dictionary that holds the user inputs for the script generated by docopt.
    layout_path : string
        Path to the target layout.

    Returns
    -------
    string
        Name of the topcell to use in run.

    """

    if arguments["--topcell"]:
        topcell = arguments["--topcell"]
    else:
        layout_topcells = get_top_cell_names(layout_path)
        if len(layout_topcells) > 1:
            logging.error(
                "## Layout has mutliple topcells. Please determine which topcell you want to run on."
            )
            exit(1)
        else:
            topcell = layout_topcells[0]

    return topcell


def generate_klayout_switches(arguments, layout_path):
    """
    parse_switches Function that parse all the args from input to prepare switches for DRC run.

    Parameters
    ----------
    arguments : dict
        Dictionary that holds the arguments used by user in the run command. This is generated by docopt library.
    layout_path : string
        Path to the layout file that we will run DRC on.

    Returns
    -------
    dict
        Dictionary that represent all run switches passed to klayout.
    """
    switches = {}

    # No. of threads
    thrCount = 2 if arguments["--thr"] is None else int(arguments["--thr"])
    switches["thr"] = str(int(thrCount))

    if arguments["--run_mode"] in ["flat", "deep", "tiling"]:
        switches["run_mode"] = arguments["--run_mode"]
    else:
        logging.error("Allowed klayout modes are (flat , deep , tiling) only")
        exit()

    if arguments["--verbose"]:
        switches["verbose"] = "true"
    else:
        switches["verbose"] = "false"

    switches["topcell"] = get_run_top_cell_name(arguments, layout_path)
    switches["input"] = layout_path

    return switches


def check_klayout_version():
    """
    check_klayout_version checks klayout version and makes sure it would work with the DRC.
    """
    # ======= Checking Klayout version =======
    klayout_v_ = os.popen("klayout -b -v").read()
    klayout_v_ = klayout_v_.split("\n")[0]
    klayout_v_list = []

    if klayout_v_ == "":
        logging.error(
            f"Klayout is not found. Please make sure klayout is installed. Current version: {klayout_v_}"
        )
        exit(1)
    else:
        klayout_v_list = [int(v) for v in klayout_v_.split(" ")[-1].split(".")]

    if len(klayout_v_list) < 1 or len(klayout_v_list) > 3:
        logging.error(
            f"Was not able to get klayout version properly. Current version: {klayout_v_}"
        )
        exit(1)
    elif len(klayout_v_list) >= 2 and len(klayout_v_list) <= 3:
        if klayout_v_list[1] < 28:
            logging.error("Prerequisites at a minimum: KLayout 0.28.0")
            logging.error(
                "Using this klayout version has not been assesed in this development. Limits are unknown"
            )
            exit(1)

    logging.info(f"Your Klayout version is: {klayout_v_}")


def check_layout_path(layout_path):
    """
    check_layout_type checks if the layout provided is GDS or OAS. Otherwise, kill the process. We only support GDS or OAS now.

    Parameters
    ----------
    layout_path : string
        string that represent the path of the layout.

    Returns
    -------
    string
        string that represent full absolute layout path.
    """

    if not os.path.isfile(layout_path):
        logging.error("## GDS file path provided doesn't exist or not a file.")
        exit(1)

    if ".gds" not in layout_path and ".oas" not in layout_path:
        logging.error(
            "## Layout is not in GDSII or OASIS format. Please use gds format."
        )
        exit(1)

    return os.path.abspath(layout_path)


def build_switches_string(sws: dict):
    """
    build_switches_string Build swtiches string from dictionary.

    Parameters
    ----------
    sws : dict
        Dictionary that holds the Antenna swithces.
    """
    switches_str = ""
    for k in sws:
        switches_str += f"-rd {k}={sws[k]} "

    return switches_str


def run_check(drc_file: str, drc_name: str, path: str, run_dir: str, sws: dict):
    """
    run_antenna_check run DRC check based on DRC file provided.

    Parameters
    ----------
    drc_file : str
        String that has the file full path to run.
    path : str
        String that holds the full path of the layout.
    run_dir : str
        String that holds the full path of the run location.
    sws : dict
        Dictionary that holds all switches that needs to be passed to the antenna checks.

    Returns
    -------
    string
        string that represent the path to the results output database for this run.

    """

    ## Using print because of the multiprocessing
    logging.info(
        "Running Global Foundries 180nm MCU {} checks on design {} on cell {}:".format(
            path, drc_name, sws["topcell"]
        )
    )

    layout_base_name = os.path.basename(path).split(".")[0]
    new_sws = sws.copy()
    report_path = os.path.join(run_dir, f"{layout_base_name}_{drc_name}.lyrdb")

    new_sws["report"] = report_path
    sws_str = build_switches_string(new_sws)

    run_str = f"klayout -b -r {drc_file} {sws_str}"

    check_call(run_str, shell=True)

    return report_path


def run_single_processor(
    arguments: dict,
    rule_deck_full_path: str,
    layout_path: str,
    switches: dict,
    drc_run_dir: str,
):
    """
    run_single_processor run the drc checks as single run.

    Parameters
    ----------
    arguments : dict
        Dictionary that holds the arguments passed to the run_drc script.
    rule_deck_full_path : str
        String that holds the path of the rule deck files.
    layout_path : str
        Path to the target layout.
    switches : dict
        Dictionary that holds all the switches that will be passed to klayout run.
    drc_run_dir : str
        Path to the run location.
    """

    list_res_db_files = []

    ## Generate run rule deck from template.
    drc_file = os.path.join(rule_deck_full_path, "generic_tech_malformed.drc")
    table_name = "main"

    ## Run Main DRC
    list_res_db_files.append(
        run_check(drc_file, table_name, layout_path, drc_run_dir, switches)
    )

    ## Check run
    check_drc_results(list_res_db_files)


def main(drc_run_dir: str, now_str: str, arguments: dict):
    """
    main function to run the DRC.

    Parameters
    ----------
    drc_run_dir : str
        String with absolute path of the full run dir.
    now_str : str
        String with the run name for logs.
    arguments : dict
        Dictionary that holds the arguments used by user in the run command. This is generated by docopt library.
    """

    # Check gds file existance
    if os.path.exists(arguments["--path"]):
        pass
    else:
        logging.error("The input GDS file path doesn't exist, please recheck.")
        exit()

    rule_deck_full_path = os.path.dirname(os.path.abspath(__file__))

    ## Check Klayout version
    check_klayout_version()

    ## Check if there was a layout provided.
    if not arguments["--path"]:
        logging.error("No provided gds file, please add one")
        exit(1)

    ## Check layout type
    layout_path = arguments["--path"]
    layout_path = check_layout_path(layout_path)

    ## Get run switches
    switches = generate_klayout_switches(arguments, layout_path)

    run_single_processor(
        arguments, rule_deck_full_path, layout_path, switches, drc_run_dir
    )


# ================================================================
# -------------------------- MAIN --------------------------------
# ================================================================

if __name__ == "__main__":
    # arguments
    arguments = docopt(__doc__, version="RUN DRC-malformed: 1.0")

    # logs format
    now_str = datetime.utcnow().strftime("drc_run_%Y_%m_%d_%H_%M_%S")

    if (
        arguments["--run_dir"] == "pwd"
        or arguments["--run_dir"] == ""
        or arguments["--run_dir"] is None
    ):
        drc_run_dir = os.path.join(os.path.abspath(os.getcwd()), now_str)
    else:
        drc_run_dir = os.path.abspath(arguments["--run_dir"])

    os.makedirs(drc_run_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[
            logging.FileHandler(os.path.join(drc_run_dir, f"{now_str}.log")),
            logging.StreamHandler(),
        ],
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%d-%b-%Y %H:%M:%S",
    )

    # Calling main function
    main(drc_run_dir, now_str, arguments)
