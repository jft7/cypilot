#!/usr/bin/env python
#
# (C) 2021 ED for Cybele Services (cf@cybele-sailing.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

# pylint: disable=invalid-name, attribute-defined-outside-init, consider-using-f-string, multiple-imports

#from turtle import heading
import cypilot.pilot_path # pylint: disable=unused-import
from cypilot.pilot_values import EnumProperty
from pilots.learningmanager.learningmanager_v2 import save_directory, model, data_directory_name, data_directory_path, list_of_data_to_learn, list_of_data_used
import time, traceback
from logger.logger import ProcessLogger as Logger
import pickle
from pilots.pilot import AutopilotPilot

from resolv import resolv180

from pilot_values import StringValue

from pilot_path import dprint as print # pylint: disable=locally-disabled, redefined-builtin

#=================================================#
# TO DO:
# Add choice of model on main page of pilot (not in client window)

dirname = data_directory_name
data_dir = data_directory_path
save_dir = save_directory
model_name = model


#=================================================#
# Algo part

class Autolearning(AutopilotPilot):
    """Class for autolearning pilot
    """
    def __init__(self, ap):
        super(Autolearning, self).__init__('learning', ap)

        ap = self.ap

        # At the moment, learning autopilot is only usable in development mode
        # To avoid loading the module in basic or advance modes, simply uncomment lines bellow
        # if ap.features.value != 'development':
        #    raise NotImplementedError
        # ---------------------------------------------------

        self.version = self.register(StringValue, 'version', 'v1')
        self.last_model_mode = None

        self.model ={}
        self.model_available = False

        self.last_value = []
        self.HdCom = 0
        self.Hd = 0

        self.data = []
        self.apmode_map = {"compass" : 0 , "wind": 1, "true wind": 2, "gps": 3}

        self.test = None

        time.sleep(1)

        self.learning_logger = Logger(dirname=dirname, sleeping_time=0.1, watchlist=(list_of_data_to_learn + list_of_data_used),
                                      autolog=True, quality=True, speed=True)
        #self.learning_logger.start()

        self.pid.append(self.learning_logger.pid)
        print('learning logger pid :', self.learning_logger.pid)

        #upload models and register them
        self.load_model()
        model_list = []
        for item in self.model:
            if "data" in item:
                pass
            else:
                model_list.append(item)

        if model_list:
            self.model_mode = self.register(EnumProperty, 'model', model_list[0], model_list, persistent=True)

        self.daemon = True

    def load_model(self):
        """Load predict model
        """
        try:
            with open(save_directory + "/" + model + ".pkl", "rb") as f:
                new_model = pickle.load(f)
            self.model = new_model
            self.model_available = True
        except FileNotFoundError:
            print('No model available yet, if try to use pilot will come back to "simple".')
        except Exception:
            print(traceback.print_exc())

    def retrieve_value(self):
        """Retrieve data from server
        """
        ap = self.ap

        self.HdCom = ap.heading_command.value
        self.Hd = ap.heading.value

        self.last_value = []
        for item in self.data:
            if item == "ap.mode":
                self.last_value.append(self.apmode_map[ap.client.values.values[item].value])
            else:
                self.last_value.append(ap.client.values.values[item].value)

    def map_model(self):
        """Map new test function and data in use if model was update from server
        """
        if self.last_model_mode != self.model_mode.value:
            self.last_model_mode = self.model_mode.value

            self.test, self.data = self.test_value_mapper(self.model_mode.value)

    def test_value_mapper(self, mod):
        """recreate test function depending of model_name send, update also list of data in use

        Args:
            mod (str): model name in server

        Returns:
            function, list: function to test prediction, list of data in use
        """
        if "heading" in mod:
            data = self.model['data_heading_model']
            test = self.test_value_heading

        elif "cmg" in mod:
            data = self.model['data_cmg_model']
            test = self.test_value_cmg

        elif "predict" in mod:
            data = self.model["data_predict_model"]
            test = self.test_value_predict

        return test, data

    def test_value_heading_cmg(self):
        ap = self.ap
        d = []
        last_command = round(ap.servo.position.value)

        self.last_value.pop()
        list_of_angle = [-10, -7, -4, -2, -1, 0, 1, 2, 4, 7, 10]
        for i in list_of_angle:
            d.append(self.last_value + [last_command+i])

        d = self.model[self.model_mode.value].predict(d)

        best_test = self.test(d[0])
        rank = 0
        for i,j in enumerate(d):
            new_test = self.test(j)
            if new_test <= best_test:
                best_test = new_test
                rank = i

        return last_command + list_of_angle[rank]



    def test_value_heading(self, value):
        return abs(resolv180(self.Hd + value - self.HdCom))

    def test_value_cmg(self, value):
        return -value

    def test_value_predict(self):
        return self.model[self.model_mode.value].predict([self.last_value])[0]

    def test_prediction(self):
        """Test heading variation prediction with heading command

        Returns:
            int: Best servo command to reach heading command
        """
        ap = self.ap

        #if predict mode:
        if "predict" in self.model_mode.value:
            #optimisation possible pour calcul du mode vent apparent
            self.last_value.append(-ap.heading_error.value)
            return round(self.test())

        #if heading or cmg mode
        return round(self.test_value_heading_cmg())

    def process(self, reset):
        """Set servo command to best prediction or angle
        If no model available, switch back to simple mode

        Args:
            reset (bool): Unused
        """
        #if super().process(reset) is False:
        #    return
        ap = self.ap

        if ap.features.value != 'development':
            print("Feature not enabled (check ap.features.value), return to simple mode")
            ap.pilot.set('simple')
            return

        if self.model_available:
            if ap.enabled.value:
                # to debug
                """
                if ap.mode.value == 'rudder angle':
                    command = -ap.heading_command.value
                    t = 0
                else: # have to test/time this
                    self.map_model()
                    self.retrieve_value()
                    t = time.monotonic()
                    command = self.test_prediction()
                    t = time.monotonic() - t
                    # will probably be inefficient in 'wind' mode

                #send command to servo
                # print(command)
                # print("Calculation time:" + str(t))
                ap.servo.position_command.set(command)
                """
                #failsafe for sailing
                try:
                    if ap.mode.value == 'rudder angle':
                        command = ap.heading_command.value
                        t = 0
                    else: # have to test/time this
                        if ap.sensors.gps.source.value == 'none':
                            raise Exception("No more GPS available")
                        self.map_model()
                        self.retrieve_value()
                        t = time.monotonic()
                        command = self.test_prediction()
                        t = time.monotonic() - t
                        # will probably be inefficient in 'wind' mode

                    #send command to servo
                    # print(command)
                    # print("Calculation time:" + str(t))
                    ap.servo.position_command.set(command)

                except Exception as e:
                    print("Failed prediction, return to simple mode")
                    print(e)
                    ap.pilot.set('simple')
                    return

        else:
            print("No model available, return to simple mode")
            ap.pilot.set('simple')
            return

#=================================================#
# Integration part

pilot = Autolearning
