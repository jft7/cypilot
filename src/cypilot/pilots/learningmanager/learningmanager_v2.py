#!/usr/bin/python3
#
# (C) 2021 ED for Cybele Services (cf@cybele-sailing.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

#Lecture pour choix de modèle
#https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.SGDRegressor.html
#https://makina-corpus.com/data-science/initiation-au-machine-learning-avec-python-la-pratique
#https://stackoverflow.com/questions/23004374/how-to-calculate-the-likelihood-of-curve-fitting-in-scipy
#https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Lasso.html
#https://maxhalford.github.io/blog/speeding-up-sklearn-single-predictions/
# piste en vrac:
#délai de prédiction/ parametre inutiule?/ rudder.speed/ moyen d'eval/ supprimer ap.mode?/ model lasso?/ SGD regressor

# pylint: disable=multiple-imports, unused-import, consider-using-f-string, invalid-name

#from compileall import compile_file
import cypilot.pilot_path # pylint: disable=unused-import
from cmath import nan
import pickle
import os
import time
import json
from sklearn.pipeline import make_pipeline, Pipeline
from sklearn.tree import DecisionTreeRegressor
from sklearn.linear_model import LinearRegression, Lasso, Ridge, LassoCV, ElasticNet, SGDRegressor, Perceptron
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, max_error, median_absolute_error
from sklearn.model_selection import train_test_split
from resolv import resolv180
from kbhit import KBHit
import numpy as np
from scipy import interpolate
from pure_sklearn.map import convert_estimator
from itertools import product

import pandas as pd
pd.options.mode.chained_assignment = None

from pilot_path import dprint as print # pylint: disable=locally-disabled, redefined-builtin
from pilot_path import PILOT_DIR

del print # disable cypilot trace

#=================================================#
# Auto learning pilot
#=================================================#
#Global data

list_of_data_used = [
    'timestamp',
    'ap.enabled',
    "ap.vmg",
    "ap.cmg",
    # "ap.sow.speed",
    "sow.speed",
    "imu.accel_X", #have to add to model
    "imu.accel_Y", #have to add to model
    "imu.accel_Z", #have to add to model
    "rudder.speed", #have to add to model
    "imu.heading",
    "gps.track",
    "perf.quality_flag",
    #"perf.SAILection"
    ]

with open(PILOT_DIR + "boat_config.json", 'r') as file:
    c = json.load(file)
    for item in c:
        list_of_data_used.append("perf.boat_config." + item)

list_of_data_to_learn_heading = [
    "ap.mode",
    "imu.pitch",
    "imu.roll",
    "imu.pitchrate",
    "imu.rollrate",
    "imu.heel",
    "imu.headingrate",
    "gps.speed",
    "wind.speed",
    "ap.true_wind_angle",
    "ap.wind_angle",
    "ap.true_wind_speed",
    "rudder.angle"
    ]

list_of_data_to_learn_predict = [
    "ap.mode",
    "imu.pitch",
    "imu.roll",
    "imu.pitchrate",
    "imu.rollrate",
    "imu.heel",
    "imu.headingrate",
    "gps.speed",
    "wind.speed",
    "ap.true_wind_angle",
    "ap.wind_angle",
    "ap.true_wind_speed",
    "rudder.angle"
    ]

list_of_data_to_learn_cmg = [
    "ap.mode",
    "imu.pitch",
    "imu.roll",
    "imu.pitchrate",
    "imu.rollrate",
    "imu.heel",
    "imu.headingrate",
    "gps.speed",
    "wind.speed",
    "ap.true_wind_angle",
    "ap.wind_angle",
    "ap.true_wind_speed",
    "ap.heading",
    "ap.heading_error",
    "rudder.angle"
    ]

list_of_data_to_learn = list(set(list_of_data_to_learn_heading + list_of_data_to_learn_cmg + list_of_data_to_learn_predict))

list_of_predict = [
        "fut_heading_var",
        "fut_rudder.angle",
        "fut_cmg"
    ]

save_directory = PILOT_DIR #os.path.dirname(os.path.abspath(__file__))
data_directory_name = 'learning_data'
data_directory_path = os.path.expanduser("~/logfiles") + "/" + data_directory_name
model = "learning_model"


#=================================================#
#Polar creation part

class Polar_Creator():
    """Class which manage polar creation from data logged"""
    def __init__(self) -> None:
        self.filepaths = []
        self.dirpath = data_directory_path
        self.data = pd.DataFrame()

        self.settings_path = PILOT_DIR + 'sailect.sailselect'
        self.interpolate_settings_path = PILOT_DIR + 'interpolate_sailect.sailselect'
        self.polar_path = PILOT_DIR + 'polar.csv'
        self.interpolate_polar_path = PILOT_DIR + 'interpolate_polar.csv'

        self.config = {}
        self.anglelist = [0] + list(range(25, 180, 5))
        self.speedlist = list(range(0, 22, 3)) + list(range(25, 40, 5)) + list(range(40, 91, 10))

        self.polar = pd.DataFrame(index=self.anglelist,columns=self.speedlist)
        self.interpolate_polar = pd.DataFrame(index=self.anglelist,columns=self.speedlist)
        self.settings = pd.DataFrame(index=self.anglelist,columns=self.speedlist)
        self.interpolar_settings = pd.DataFrame(index=self.anglelist,columns=self.speedlist)

    def process(self):
        self.retrieve_filepaths()
        self.retrieve_config()
        for path in self.filepaths:
            self.retrieve_data(path)

        self.create_polar()
        self.create_interpolate_polar()
        self.register_polar()

    def retrieve_filepaths(self):
        self.filepaths = sorted([(self.dirpath + '/' + f) for f in os.listdir(self.dirpath) if f.endswith('.csv')])

    def retrieve_config(self):
        with open(PILOT_DIR + "boat_config.json", 'r') as f:
            self.config = json.load(f)

    def retrieve_data(self, path):
        """Function wich retrieve data from file, add feature and process data
        Args:
            path (str): Filepath
        """
        try:
            d = pd.read_csv(path)
            d = self.process_data(d)

        except KeyError:
            d = pd.DataFrame()
        except Exception as e:
            print("Fail to process data on file {}\n {}".format(path, e))

        try:
            self.data = pd.concat([self.data,d])

        except:
            pass

    def process_data(self, d):
        """Clean data and add feature
        """
        lod = [
            "ap.true_wind_speed",
            "ap.true_wind_angle",
            # "ap.sow.speed",
            "sow.speed"
        ]

        for itm in self.config:
            lod.append("perf.boat_config." + itm)

        try:
            d = d.drop(d[d['perf.quality_flag'] != True].index)
            d = d[lod]
            d.convert_dtypes()

            d[ "ap.true_wind_speed"] = d[ "ap.true_wind_speed"].round()
            d[ "ap.true_wind_angle"] = d[ "ap.true_wind_angle"].round()
            
            d = d.replace([None, False, "False", "none"], np.nan)
            d = d.dropna(axis='index')
            return d

        except KeyError:
            return pd.DataFrame(columns=lod)

    def format_setting(self, setting):
        text = str()
        try:
            last = len(setting) - 1
            for rank, itm in enumerate(setting):
                text += itm[0] + ": " + itm[1]
                if rank != last:
                    text += " | "
            return text

        except TypeError:
            return None

    def create_polar(self):
        # to take every combination possible
        print("Polar creation in porgress.")
        iteration = []
        for key in self.config:
            it = []
            for value in self.config[key]:
                it.append((key, value))
            iteration.append(it)
        iteration = list(product(*iteration))


        # then use loc to select
        for a in self.anglelist:
            for s in self.speedlist:
                #add try except to set to none if no sufficient data
                print( "Processing polar for angle and windspeed : ", a, s)
                lastpercentile = 0
                try:
                    if a == 0 or s ==0:
                        lastpercentile = 1
                        self.polar[s][a] = 0
                        self.settings[s][a] = "none"
                    else:
                        workdf = self.data.loc[((self.data["ap.true_wind_angle"] == a) | (self.data["ap.true_wind_angle"] == -a)) & (self.data["ap.true_wind_speed"] == s)]
                        if not workdf.empty :
                            print("   ---> some values match, updating polar file")
                        for conf in iteration:
                            tempdf = workdf
                            for i in conf:
                                kp = 'perf.boat_config.'+i[0]
                                tempdf[kp] = tempdf[kp].apply(str)                              
                                tempdf = tempdf.loc[tempdf[kp] == i[1]]
                            if len(tempdf) >0:
                                # percentile = tempdf["ap.sow.speed"].quantile(0.95)
                                percentile = tempdf["sow.speed"].quantile(0.95)
                                if percentile > lastpercentile:
                                    lastpercentile = percentile
                                    self.polar[s][a] = percentile
                                    self.settings[s][a] = self.format_setting(conf)
                                else:
                                    pass

                except KeyError:
                    pass

                if lastpercentile == 0:
                    self.polar[s][a] = None
                    self.settings[s][a] = None

    def create_interpolate_polar(self):
        count = 0
        self.interpolate_polar = self.polar.copy()
        while self.interpolate_polar.isnull().values.any():

            if count > 2:
                #to be sure to exit if there is no data
                break

            count += 1
            for ind in self.interpolate_polar.index:
                work_row = self.interpolate_polar.loc[[ind]]
                work_row = work_row.dropna(axis='columns')
                try:
                    work_f = interpolate.interp1d(work_row.columns,work_row.to_numpy(), kind='cubic', bounds_error=False, fill_value="extrapolate" )
                    for col in self.interpolate_polar.columns:
                        if col == 0 or ind == 0:
                            self.interpolate_polar[col][ind] = 0
                        else:
                            self.interpolate_polar[col][ind] = max(round(work_f(col)[0], 2), 0)
                except ValueError:

                    pass

            for col in self.interpolate_polar.columns:
                work_col = self.interpolate_polar[col]
                work_col = work_col.dropna(axis='index')
                try:
                    work_f = interpolate.interp1d(work_col.index,work_col.values, kind='cubic', bounds_error=False, fill_value="extrapolate" )
                    for ind in self.interpolate_polar.index:
                        if col == 0 or ind == 0:
                            self.interpolate_polar[col][ind] = 0
                        else:
                            self.interpolate_polar[col][ind] = max(round(work_f(ind).tolist(), 2), 0)
                except ValueError:
                    pass

        #interpolate settings to nearest value
        self.interpolate_settings = self.settings.replace([None], np.nan)
        count = 0
        while self.interpolate_settings.isnull().values.any():
            if count > 10:
                #to be sure to exit if there is no data
                break
            count += 1

            self.interpolate_settings.fillna(method="ffill", axis="index")
            self.interpolate_settings.fillna(method="bfill", axis="index")
            self.interpolate_settings.fillna(method="ffill", axis="columns")
            self.interpolate_settings.fillna(method="bfill", axis="columns")

    def register_polar(self):
        self.polar.to_csv(self.polar_path, sep=';', na_rep='None', index_label="TWA\\TWS")
        self.interpolate_polar.to_csv( self.interpolate_polar_path, sep=';', na_rep='None', index_label='TWA\\TWS')
        self.settings.to_csv(self.settings_path, sep=';', na_rep='None', index_label="TWA\\TWS",)
        self.interpolate_settings.to_csv(self.interpolate_settings_path, sep=';', na_rep='None', index_label="TWA\\TWS",)
        print("New polar and setting guide updated.")
#=================================================#
#Learning part

class NoValidDataError(Exception):
    '''raise this when there's no valid data in the file'''
    pass

class Learning_class():
    """Class which manage learning from data logged
    """
    def __init__(self, prediction_time=10):
        """Init dirpath and value

        Args:
            list_of_data_to_learn (list of str): list of item needed from server to learn/predict
            list_of_data_usefull (list of str): list of item needed from server to use learning process learning data
        """
        self.quality = False
        self.filepaths = []
        self.data = pd.DataFrame()
        self.model_name = model
        self.X0_heading = False
        self.X0_cmg = False
        self.X0_predict = False
        self.y0_heading = False
        self.y0_cmg = False
        self.y0_predict = False
        self.model_dict = {}
        self.dirpath = data_directory_path
        self.savedir = save_directory
        self.prediction_time = int(prediction_time)
        self.datacount = 0
        self.model_loaded = {}

        self.define_model()

    def retrieve_data(self, path):
        """Function wich retrieve data from file, add feature and process data

        Args:
            path (str): Filepath
        """
        try:
            d = pd.read_csv(path)
            d = self.process_data(d)

        except KeyError:
            d = pd.DataFrame()
        except Exception as e:
            print("Fail to process data on file {}\n {}".format(path, e))      
        
        try:
            self.data = d
            self.define_data()

        except Exception as e:
            pass
        
        return len(d)


    def process_learning(self):
        """Update dataframe from data
        """
        self.retrieve_filepaths()
        self.update_scaler()
        self.update_model()
        self.finish_model()
        return True


    def retrieve_filepaths(self):
        self.filepaths = sorted([(self.dirpath + '/' + f) for f in os.listdir(self.dirpath) if f.endswith('.csv')])

    def update_scaler(self, limit=0):
        l = len(self.filepaths)
        list_of_unvalid_data_path_index = []
        try:
            for i, p in enumerate(self.filepaths):
                print("Fit scaler on file n°{}/{}. \n{}".format(i+1,l,p))
                #test if data of the file is useful and keep the index if not
                if self.retrieve_data(p) == 0:
                    list_of_unvalid_data_path_index.append(i)
                self.fit_scaler(p)
                if limit != 0 and self.datacount>=limit:
                    break
            #remove all unused file for ulterior processing for model
            for i in sorted(list_of_unvalid_data_path_index, reverse=True):
                del self.filepaths[i]


        except TypeError as e:#ValueError
            print("No file to learn")
            raise ValueError("No file to learn.")from e

    def update_model(self, limit=0):
        l = len(self.filepaths)
        try:
            for i, p in enumerate(self.filepaths):
                print("Fit models on file n°{}/{}. \n{}".format(i+1,l,p))
                self.retrieve_data(p)
                self.fit_model(p)
                if limit != 0 and self.datacount>=limit:
                    break                    

        except ValueError as e:
            print("No file to learn")
            raise ValueError("No file to learn.")from e

    def update_data(self, limit=0):
        l = len(self.filepaths)
        try:
            for i, p in enumerate(self.filepaths):
                print("Retrieve data on file n°{}/{}. \n{}".format(i,l,p))
                self.retrieve_data(p)
                if limit != 0 and self.datacount>=limit:
                    print("Reach enough data to perform test")
                    break
        except ValueError as e:
            print("No file to learn")
            raise ValueError("No file to learn.")from e

    def test_model(self):
        """Test and train model
        """
        text = ""
        try:

            for item in self.model_loaded:
                #optimisable
                if "heading" in item:
                    val_X0, val_y0 = self.X0_heading, self.y0_heading
                elif "predict" in item:
                    val_X0, val_y0 = self.X0_predict, self.y0_predict
                elif "cmg" in item:
                    val_X0, val_y0 = self.X0_cmg, self.y0_cmg

                predict_value = self.model_loaded[item].predict(val_X0)

                text += ("_____" + item + "_____\n"+
                    "MeanAE : " +
                    str(mean_absolute_error(val_y0, predict_value)) + "\n" +
                    "MedianAE : " +
                    str(median_absolute_error(val_y0, predict_value)) + "\n" +
                    "MeanSqrE : " +
                    str(mean_squared_error(val_y0, predict_value)) + "\n" +
                    "MaxE : " +
                    str(max_error(val_y0, predict_value)) + "\n")

                try:
                    importance = self.model_loaded[item][1].coef_
                    t = "Coefficients:\n"
                    if "heading" in item:
                        for i, v in enumerate(importance):
                            t += list_of_data_to_learn_heading[i] + " : " + str(v) +"\n"
                    elif "cmg" in item:
                        for i, v in enumerate(importance):
                            t += list_of_data_to_learn_cmg[i] + " : " + str(v) +"\n"
                    t += "\n"
                    text += t

                except AttributeError:
                    pass

                try:
                    importance = self.model_loaded[item][1].feature_importances_
                    t = "Feature importances:\n"
                    if "heading" in item:
                        for i, v in enumerate(importance):
                            t += list_of_data_to_learn_heading[i] + " : " + str(v) +"\n"
                    elif "cmg" in item:
                        for i, v in enumerate(importance):
                            t += list_of_data_to_learn_cmg[i] + " : " + str(v) +"\n"
                    t += "\n"
                    text += t

                except AttributeError:
                    pass

        except ValueError as e:
            print(e)
            text += "Not enough valid data to test a prediction model"

        print(text)
        return text



    def process_data(self, d):
        """Clean data and add feature
        """
        lod = list_of_data_to_learn + list_of_data_used + list_of_predict
        for item in lod:
            if item not in d.columns:
                d[item] = np.nan
        d = d[lod]
        d.convert_dtypes()
        d['ap.enabled'] = d['ap.enabled'].astype('bool')
        
        # create new feature fut_heading_var
        d['fut_heading_var'] = d['imu.heading'].shift(-self.prediction_time) - d['imu.heading']
        d['fut_heading_var'] = d['fut_heading_var'].apply(resolv180)

        #create new feature fut_rudder.angle
        d['fut_rudder.angle'] = d['rudder.angle'].shift(round(-self.prediction_time/2))

        # create new feature fut_cmg
        d['fut_cmg'] = d['ap.cmg'].shift(-10)

        #check quality
        if self.quality == True:
            d = d.drop(d[d['perf.quality_flag'] != True].index)

        # convert ap.mode data
        d['ap.mode'].replace({"compass" : 0 , "wind": 1, "true wind": 2, "gps": 3}, inplace=True)

        # clean data
        d = d.drop(d[d['gps.speed'].apply(lambda x: isinstance(x, str))].index)
        d = d.drop(d[d['gps.speed'] < 1.0].index)
        d = d.drop(d[(d['ap.mode'] == "rudder angle") & (d['ap.enabled']== "False")].index)

        d = d.drop(list_of_data_used, axis=1) #remove unused data

        d = d.replace(['False', 'none'] , np.nan)
        #if not working use this
        #d = d.replace({'False' : np.nan})
        #d = d.replace({'none' : np.nan})
        d = d.dropna(axis=0)

        self.datacount += len(d)

        return d


    def define_data(self):
        """Define y0 et X0
        """
        self.y0_heading = self.data['fut_heading_var']
        self.y0_cmg = self.data['fut_cmg']
        self.y0_predict = self.data['fut_rudder.angle']

        l = list_of_data_to_learn_heading.copy()
        l.pop()
        l = l + ['fut_rudder.angle']
        self.X0_heading = self.data[l]
        self.X0_heading = self.X0_heading.reindex(columns=l)

        l = list_of_data_to_learn_predict.copy() + ['fut_heading_var']
        self.X0_predict = self.data[l]
        self.X0_predict = self.X0_predict.reindex(columns=l)

        l = list_of_data_to_learn_cmg.copy()
        l.pop()
        l = l + ['fut_rudder.angle']
        self.X0_cmg = self.data[l]
        self.X0_cmg = self.X0_cmg.reindex(columns=l)


    def define_model(self):
        """Define model
        """
        model_list = [MLPRegressor] #LassoCV, SGDRegressor, Lasso, ElasticNet, LinearRegression,Ridge, DecisionTreeRegressor, Perceptron, MLPRegressor]
        self.model_dict = {}
        for mod in model_list:
            if hasattr(mod(), "penalty"):
                self.model_dict[(mod.__name__+"_heading_model")] = [StandardScaler(), mod(penalty='elasticnet')]
                self.model_dict[(mod.__name__+"_cmg_model")] = [StandardScaler(),mod(penalty='elasticnet')]
                self.model_dict[(mod.__name__+"_predict_model")] = [StandardScaler(),mod(penalty='elasticnet')]
            else:
                self.model_dict[(mod.__name__+"_heading_model")] = [StandardScaler(), mod()]
                self.model_dict[(mod.__name__+"_cmg_model")] = [StandardScaler(),mod()]
                self.model_dict[(mod.__name__+"_predict_model")] = [StandardScaler(),mod()]

    def fit_scaler(self, file):
        """Fit data to scaler"""
        try:
            for item in self.model_dict:
                if "heading" in item:
                    self.model_dict[item][0].partial_fit(self.X0_heading.values)
                elif "predict" in item:
                    self.model_dict[item][0].partial_fit(self.X0_predict.values)
                elif "cmg" in item:
                    self.model_dict[item][0].partial_fit(self.X0_cmg.values)

        except ValueError as e:
            pass
        except AttributeError:
            pass
        except Exception as e:
            print("Fail to fit scaler on file {}\n {}".format(file, e))


    def fit_model(self, file):
        """Fit data to model
        """
        try:
            for item in self.model_dict:
                if hasattr(self.model_dict[item][1], "partial_fit"):
                    if "heading" in item:
                        self.model_dict[item][1].partial_fit(self.model_dict[item][0].transform(self.X0_heading.values), self.y0_heading.values)
                    elif "predict" in item:
                        self.model_dict[item][1].partial_fit(self.model_dict[item][0].transform(self.X0_predict.values), self.y0_predict.values)
                    elif "cmg" in item:
                        self.model_dict[item][1].partial_fit(self.model_dict[item][0].transform(self.X0_cmg.values), self.y0_cmg.values)
                else:
                    if "heading" in item:
                        self.model_dict[item][1].fit(self.model_dict[item][0].transform(self.X0_heading.values), self.y0_heading.values)
                    elif "predict" in item:
                        self.model_dict[item][1].fit(self.model_dict[item][0].transform(self.X0_predict.values), self.y0_predict.values)
                    elif "cmg" in item:
                        self.model_dict[item][1].fit(self.model_dict[item][0].transform(self.X0_cmg.values), self.y0_cmg.values)

        except ValueError as e:
            pass
        except Exception as e:
            print("Fail to fit model on file {}\n {}".format(file, e))

    def finish_model(self):
        for item in self.model_dict:
            self.model_dict[item] = make_pipeline(self.model_dict[item][0], self.model_dict[item][1])

    def load_model(self):
        """Load model function
        """
        with open(self.savedir + "/" + self.model_name + ".pkl", "rb") as f:
            self.model_loaded = pickle.load(f)
            self.model_loaded.pop('data_heading_model')
            self.model_loaded.pop('data_cmg_model')
            self.model_loaded.pop('data_predict_model')

    def register_model(self):
        """Register model function
        """
        #try:
        model_and_datalist = {
            'data_heading_model' : list_of_data_to_learn_heading,
            'data_cmg_model' : list_of_data_to_learn_cmg,
            'data_predict_model' : list_of_data_to_learn_predict
        }

        for item in self.model_dict:
            model_and_datalist[item] = self.model_dict[item]
            #try:
                #model_and_datalist[item] = convert_estimator(self.model_dict[item])
            #except ValueError:
                #print(item + " not in pure_predict, python function will be registered")
                #model_and_datalist[item] = self.model_dict[item]

        with open(self.savedir + "/" + self.model_name + ".pkl", "wb") as f:
            pickle.dump(model_and_datalist, f)
            
        if self.datacount != 0:
            print("Prediction model updated. \n{} line of data processed.".format(str(round(self.datacount/2))))
        else:
            print("Not enough valid data to update model")

        #except AttributeError as e:
        #    print("{}. \nPrediction model not updated.".format(e))

    def process(self):
        """Wrap all function to record new model
        """
        print('Retrieving data from {}'.format(self.dirpath))
        if self.process_learning():
            print('Are you sure to change to this new model? The old one will be overriden. y/n')
            while True:
                if not kb.kbhit():
                    time.sleep(0.3)
                else:
                    k = kb.getch()
                    if k == 'y':
                        print('Registering new model...')
                        self.register_model()
                        
                        break
                    elif k == 'n':
                        print('Model update canceled')
                        break
            print('Finish')

learning = Learning_class()
polar = Polar_Creator()

#=================================================#
# Minimal GUI

if __name__ == "__main__":
    #learning.load_model()
    print('To update autopilot learning model with only quality data press "u", with all data press "a". \n')
    print('To update polar and sailect press "p"\n')
    print('Else press "q" or quit this window')
    kb = KBHit()
    while True:
        if not kb.kbhit():
            time.sleep(0.3)
        else:
            k = kb.getch()
            if k == 'q':
                break
            elif k == 'p':
                print("Trying to update polar and sailect, this could take some time, please wait...")
                polar.process()

            elif k == 'u':
                print("Trying to update learning model with only quality labeled data, this could take some time, please wait...")
                learning.quality = True
                learning.process()
            elif k == 'a':
                print("Trying to update learning model with all data, this could take some time, please wait...")
                learning.quality = False
                learning.process()

#============
