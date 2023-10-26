#!/usr/bin/python3
import os
import shutil
import time
import pandas as pd
pd.options.mode.chained_assignment = None

import cypilot.pilot_path
from kbhit import KBHit

data_directory_path = os.path.expanduser("~/logfiles") + "/learning_data"
save_directory_path = os.path.expanduser("~/logfiles") + "/learning_data_bak"

class LogfileUpdater():
    """Class which updates and cleans logfiles"""
    def __init__(self) -> None:
        self.filepaths = []
        self.dirpath = data_directory_path
        self.data = pd.DataFrame()
        self.filepaths = sorted([(self.dirpath + '/' + f) for f in os.listdir(self.dirpath) if f.endswith('.csv')])
        if not os.path.exists(save_directory_path):
            os.makedirs(save_directory_path)

    def process_quality_flag(self):
        nf = len(self.filepaths)
        nc = 1
        print("Processing {} files ...".format(nf))
        for path in self.filepaths:
            print("{}/{}".format(nc,nf),end='\r')
            nc += 1
            try:
                d = pd.read_csv(path)
            except Exception as e:
                print("Fail to read data from file {}\n {}".format(path, e))

            qf = d.get('perf.quality_flag')
            if(qf is not None):
                d = d.drop(d[d['perf.quality_flag'] != True].index)

            if(len(d) == 0 or qf is None):
                try:
                    shutil.move(path,save_directory_path)
                except FileExistsError:
                    pass
                except Exception as e:
                    print("Fail to move file {}\n {}".format(path, e))

    def process_rollrate_pitchrate(self):
        nf = len(self.filepaths)
        nc = 1
        print("Processing {} files ...".format(nf))
        for path in self.filepaths:
            print("{}/{}".format(nc,nf),end='\r')
            nc += 1
            try:
                d = pd.read_csv(path)
            except Exception as e:
                print("Fail to read data from file {}\n {}".format(path, e))

            year,month,day=time.localtime(os.path.getmtime(path))[:-6]
            ld = f'{year}'+f'{month:02d}'+f'{day:02d}'
            nr = len(d)
            if (int(ld) < 20230803) and (nr > 2):

                try:
                    for index in range(0,nr-1):
                        d['imu.rollrate'][index]=round((d['imu.roll'][index+1]-d['imu.roll'][index])/.1,3)
                        d['imu.pitchrate'][index]=round((d['imu.pitch'][index+1]-d['imu.pitch'][index])/.1,3)
                    d['imu.rollrate'][nr-1]=d['imu.rollrate'][nr-2]
                    d['imu.pitchrate'][nr-1]=d['imu.pitchrate'][nr-2]
                except:
                    continue
                
                dest = path[:-4]+'-r.csv'
                d.to_csv(dest,index=False)

                try:
                    shutil.move(path,save_directory_path)
                except FileExistsError:
                    pass
                except Exception as e:
                    print("Fail to move file {}\n {}".format(path, e))

if __name__ == "__main__":
    lu = LogfileUpdater()
    print('\nHit a key to update logfiles:')
    print(' - f : keep file only if it contains a record with perf.quality_flag True')
    print(' - r : fix rollrate and pitchrate values (only files older than August 3rd 2023)')
    print(' - q : exit\n\n')
    kb = KBHit()
    while True:
        if not kb.kbhit():
            time.sleep(0.3)
        else:
            k = kb.getch()
            if k == 'q':
                break
            elif k == 'r':
                lu.process_rollrate_pitchrate()
            elif k == 'f':
                lu.process_quality_flag()
