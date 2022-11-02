import argparse
import csv
import logging
import os
import pickle
import time

import numpy as np
import pandas as pd

import Cptool
import ModelFit
from Cptool.config import toolConfig
from Cptool.gaMavlink import GaMavlinkAPM, GaMavlinkPX4
from Cptool.gaSimManager import GaSimManager


# from Cptool.gaSimManager import GaSimManager
from uavga.fuzzer import return_random_n_gen, return_cluster_thres_gen

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Personal information')
    parser.add_argument('--device', dest='device', type=str, help='Name of the candidate')
    args = parser.parse_args()
    device = args.device
    if device is None:
        device = 0
    print(device)

    toolConfig.select_mode("PX4")

    # Get Fuzzing result and validate
    with open(f'result/{toolConfig.MODE}/pop{toolConfig.EXE}.pkl', 'rb') as f:
        candidate_obj, candidate_var = pickle.load(f)

    # Simulator validation
    manager = GaSimManager(debug=toolConfig.DEBUG)

    i = 0
    # Random order
    rand_index = (np.arange(candidate_obj.shape[0]))
    np.random.shuffle(rand_index)
    candidate_obj = candidate_obj[rand_index]
    candidate_var = candidate_var[rand_index]

    # Loop to validate configurations with SITL simulator
    for index, vars, value_vector in zip(np.arange(candidate_obj.shape[0]), candidate_var, candidate_obj):
        print(f'======================={index} / {candidate_obj.shape[0]} ==========================')
        # if exist file, append new data in the end.
        if os.path.exists(f'result/{toolConfig.MODE}/params{toolConfig.EXE}.csv'):
            while not os.access(f"result/{toolConfig.MODE}/params{toolConfig.EXE}.csv", os.R_OK):
                continue
            data = pd.read_csv(f'result/{toolConfig.MODE}/params{toolConfig.EXE}.csv')
            exit_data = data.drop(['score', 'result'], axis=1, inplace=False)
            # carry our simulation test
            if ((exit_data - value_vector).sum(axis=1).abs() < 0.00001).sum() > 0:
                continue

        configuration = pd.Series(value_vector, index=toolConfig.PARAM_PART).to_dict()
        # start multiple SITL
        manager.start_multiple_sitl(device)
        manager.start_multiple_sim(device)
        manager.mav_monitor_init(GaMavlinkPX4, device)

        if not manager.mav_monitor_connect():
            manager.stop_sitl()
            continue

        manager.mav_monitor.set_mission("Cptool/fitCollection_px4.txt", israndom=False)
        manager.mav_monitor.set_params(configuration)

        time.sleep(2)
        manager.mav_monitor.start_mission()
        # File
        manager.mav_monitor.init_ulg_log_file(device)
        result = manager.mav_monitor_error()

        # if the result have no instability, skip.
        if not os.path.exists(f'result/{toolConfig.MODE}/params{toolConfig.EXE}.csv'):
            while not os.access(f"result/{toolConfig.MODE}/params{toolConfig.EXE}.csv", os.W_OK):
                time.sleep(0.1)
                continue
            data = pd.DataFrame(columns=(toolConfig.PARAM + ['score', 'result']))
        else:
            while not os.access(f"result/{toolConfig.MODE}/params{toolConfig.EXE}.csv", os.W_OK):
                time.sleep(0.1)
                continue
            # Add instability result
            tmp_row = value_vector.tolist()
            tmp_row.append(vars[0])
            tmp_row.append(result)

            # Write Row
            with open(f"result/{toolConfig.MODE}/params{toolConfig.EXE}.csv", 'a+') as f:
                csv_file = csv.writer(f)
                csv_file.writerow(tmp_row)
                logging.debug(f"Write row to params{toolConfig.EXE}.csv.")

        manager.stop_sitl()
        manager.stop_sim()
        i += 1
        time.sleep(1)

        # Delete Log
        if os.path.exists(manager.mav_monitor.log_file):
            os.remove(manager.mav_monitor.log_file)


    localtime = time.asctime(time.localtime(time.time()))
    # Mail notification plugin
    # send_mail(Cptool.config.AIRSIM_PATH, localtime)