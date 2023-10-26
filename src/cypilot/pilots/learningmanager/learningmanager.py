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

# pylint: disable=multiple-imports, unused-import, consider-using-f-string, invalid-name, redefined-outer-name

#from compileall import compile_file
import cypilot.pilot_path
import pickle
import os
import time
from sklearn.pipeline import make_pipeline
from sklearn.tree import DecisionTreeRegressor
from sklearn.linear_model import LinearRegression, Lasso, Ridge, LassoCV, ElasticNet, SGDRegressor, Perceptron
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, max_error, median_absolute_error
from sklearn.model_selection import train_test_split
from resolv import resolv180
from kbhit import KBHit
import numpy as np
from pure_sklearn.map import convert_estimator

import pandas as pd

from pilot_path import dprint as print # pylint: disable=locally-disabled, redefined-builtin
from pilot_path import PILOT_DIR

#=================================================#
# Auto learning pilot
#=================================================#
#Global data

list_of_data_used = [
    'ap.enabled',
    "ap.vmg",
    "ap.cmg",
    "imu.accel_X", #have to add to model
    "imu.accel_Y", #have to add to model
    "imu.accel_Z", #have to add to model
    "rudder.speed", #have to add to model
    "imu.heading",
    "gps.track"
    ]

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
#Learning part

class Learning_class():
    """Class which manage learning from data logged
    """
    def __init__(self, prediction_time=10):
        """Init dirpath and value

        Args:
            list_of_data_to_learn (list of str): list of item needed from server to learn/predict
            list_of_data_usefull (list of str): list of item needed from server to use learning process learning data
        """
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

    def retrieve_data(self, path):
        """Function wich retrieve data from file and add feature

        Args:
            path (str): Filepath

        Returns:
            Panda.DataFrame: DataFrame from csv file + feature
        """
        try:
            d = pd.read_csv(path)
            # create new feature fut_heading_var
            d['fut_heading_var'] = d['imu.heading'].shift(-self.prediction_time) - d['imu.heading']
            d['fut_heading_var'] = d['fut_heading_var'].apply(resolv180)

            #create new feature fut_rudder.angle
            d['fut_rudder.angle'] = d['rudder.angle'].shift(round(-self.prediction_time/2))

            # create new feature fut_cmg
            d['fut_cmg'] = d['ap.cmg'].shift(-10)

        except KeyError:
            d = pd.DataFrame()

        return d

    def update_data(self):
        """Update dataframe from data
        """
        self.filepaths = sorted([(self.dirpath + '/' + f) for f in os.listdir(self.dirpath) if f.endswith('.csv')])
        try:
            self.data = pd.concat(map(self.retrieve_data, self.filepaths), ignore_index=True)
            return True
        except ValueError as e:
            print("No file to learn")
            raise ValueError("No file to learn.")from e

    def process_data(self):
        """Clean data and add feature
        """
        # need to check shift method
        lod = list_of_data_to_learn + list_of_data_used + list_of_predict
        self.data = self.data[pd.Index(lod)]
        self.data.convert_dtypes()
        self.data['ap.enabled'] = self.data['ap.enabled'].astype('bool')

        # convert ap.mode data
        self.data['ap.mode'].replace({"compass" : 0 , "wind": 1, "true wind": 2, "gps": 3}, inplace=True)

        # clean data
        self.data = self.data.drop(self.data[self.data['gps.speed'].apply(lambda x: isinstance(x, str))].index)
        self.data = self.data.drop(self.data[self.data['gps.speed'] < 1.0].index)
        self.data = self.data.drop(self.data[self.data['ap.mode'] == "rudder angle"].index) # remove data if ap.mode is rudder

        self.data = self.data.drop(list_of_data_used, axis=1) #remove unused data

        self.data = self.data.replace({'False' : np.nan})
        self.data = self.data.dropna(axis=0)

        print("Process data, len : {}".format(len(self.data)))


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
        model_list = [LinearRegression, ElasticNet, MLPRegressor] #LassoCV, Lasso, SGDRegressor,Ridge, DecisionTreeRegressor, Perceptron, MLPRegressor]
        self.model_dict = {}
        for mod in model_list:
            self.model_dict[(mod.__name__+"_heading_model")] = make_pipeline(StandardScaler(),mod())
            self.model_dict[(mod.__name__+"_cmg_model")] = make_pipeline(StandardScaler(),mod())
            self.model_dict[(mod.__name__+"_predict_model")] = make_pipeline(StandardScaler(),mod())

    def fit_model(self):
        """Fit data to model
        """
        try:
            for item in self.model_dict:
                if "heading" in item:
                    self.model_dict[item].fit(self.X0_heading.values, self.y0_heading.values)
                elif "predict" in item:
                    self.model_dict[item].fit(self.X0_predict.values, self.y0_predict.values)
                elif "cmg" in item:
                    self.model_dict[item].fit(self.X0_cmg.values, self.y0_cmg.values)

        except ValueError as e:
            print(e)
            print("Not enough valid data to train a prediction model")



    def test_model(self):
        """Test and train model
        """
        text = ""
        try:
            htrain_X0, hval_X0, htrain_y0, hval_y0 = train_test_split(self.X0_heading, self.y0_heading, random_state=0)
            ctrain_X0, cval_X0, ctrain_y0, cval_y0 = train_test_split(self.X0_cmg, self.y0_cmg, random_state=0)
            ptrain_X0, pval_X0, ptrain_y0, pval_y0 = train_test_split(self.X0_predict, self.y0_predict, random_state=0)

            for item in self.model_dict:
                #optimisable
                if "heading" in item:
                    train_X0, val_X0, train_y0, val_y0 = htrain_X0, hval_X0, htrain_y0, hval_y0
                elif "predict" in item:
                    train_X0, val_X0, train_y0, val_y0 = ptrain_X0, pval_X0, ptrain_y0, pval_y0
                elif "cmg" in item:
                    train_X0, val_X0, train_y0, val_y0 = ctrain_X0, cval_X0, ctrain_y0, cval_y0

                self.model_dict[item].fit(train_X0, train_y0)
                predict_value = self.model_dict[item].predict(val_X0)

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
                    importance = self.model_dict[item][1].coef_
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
                    importance = self.model_dict[item][1].feature_importances_
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


    def register_model(self):
        """Register model function
        """
        try:
            model_and_datalist = {
                'data_heading_model' : list_of_data_to_learn_heading,
                'data_cmg_model' : list_of_data_to_learn_cmg,
                'data_predict_model' : list_of_data_to_learn_predict
            }
            for item in self.model_dict:
                try:
                    model_and_datalist[item] = convert_estimator(self.model_dict[item])
                except ValueError:
                    print(item + " not in pure_predict, python function will be registered")
                    model_and_datalist[item] = self.model_dict[item]

            with open(self.savedir + "/" + self.model_name + ".pkl", "wb") as f:
                pickle.dump(model_and_datalist, f)

            print("Prediction model updated.")

        except AttributeError as e:
            print(e)
            print("Prediction model not updated.")

    def process(self):
        """Wrap all function to record new model
        """
        print('Retrieving data from {}'.format(self.dirpath))
        if self.update_data():
            print("Processing data...")
            self.process_data()
            print("Defining new features...")
            self.define_data()
            print("Defining model...")
            self.define_model()
            print("Testing model...")
            self.test_model()
            print('Are you sure to change to this new model? The old one will be overriden. y/n')
            while True:
                if not kb.kbhit():
                    time.sleep(0.3)
                else:
                    k = kb.getch()
                    if k == 'y':
                        print('Finishing new model...')
                        self.fit_model()
                        print('Registering new model...')
                        self.register_model()
                        print('New model registered.')
                        break
                    elif k == 'n':
                        print('Model update canceled')
                        break
            print('Finish')

learning = Learning_class()

#=================================================#
# Minimal GUI

if __name__ == "__main__":
    print('To update autopilot learning model press "u", else press "q" or quit this window')
    kb = KBHit()
    while True:
        if not kb.kbhit():
            time.sleep(0.3)
        else:
            k = kb.getch()
            if k == 'q':
                break
            elif k == 'u':
                print("Trying to update learning model, this could take some time, please wait...")
                learning.process()

#============
