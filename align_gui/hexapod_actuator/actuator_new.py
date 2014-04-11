"""
actuator.py
"""

import ConfigParser
import os.path
import numpy
import wx

from capgauge import CompositeCapgauge
from picomotor import PicomotorWeb
from motorleg import MotorLeg, CompositeMotorLegs
from actuator_wx import HexapodActuatorWxScrolledPanel, ActuatorDoneEvent

class HexaPodActuatorException(Exception):
	"""
	@Purpose:
		customized HexaPodActuatorException
	"""
	def __init__(self, expr, msg):
		self.expr = expr
		self.msg = msg
	
	def __str__(self):
		return "ERROR: HexaPodActuatorException.\n expression = %s.\n %s\n" % (repr(self.expr), self.msg)	


class HexaPodActuator(object):
	"""
	@Purpose:
		create a HexPod class that can controll the all the sensors and motors on a HexPod machine
	"""
	def __init__(self, capgauge_config, picomotor_controllers, calibrate_config='hexapod_calibrate.cfg', move_widget=None):
		"""
		@Purpose:
			Constructor
		@Inputs:
			(str) capgauge_config = path to NI capgauge controller config file.
			(list) picomotor_controllers = list of picomotor hostnames or ip addresses.
			(str) calibrate_config = saved hexapod calibration configuration file
			(wx_extensions.dialogs.DialogProgress) logGUIWidget = wxPython extended dialog to show details of movements.
		"""
		if move_widget != None:
			assert isinstance(move_widget, HexapodActuatorWxScrolledPanel), "move_widget is %s, but it's required to be HexapodActuatorWxScrolledPanel" % repr(type(move_widget))
		self.moveWidget = move_widget
		######### STOP FLAG: Interrupt legChange or capChange ########
		self.__stop__ = False
		##############################################################
		######### IsCompositeCapgauge FLAG: determine if we are using the CompositeCapgauge ########
		self.__isCompositeCapgauge__ = True
		############################################################################################
		picomotor1 = PicomotorWeb(picomotor_controllers[0])
		picomotor2 = PicomotorWeb(picomotor_controllers[1])
		self.picomotors = [picomotor1, picomotor2]

		"""
		cap0 = Capgauge(0, ni_config_file=capgauge_config, name='leg0')
		cap1 = Capgauge(1, ni_config_file=capgauge_config, name='leg1')
		cap2 = Capgauge(2, ni_config_file=capgauge_config, name='leg2')
		cap3 = Capgauge(3, ni_config_file=capgauge_config, name='leg3')
		cap4 = Capgauge(4, ni_config_file=capgauge_config, name='leg4')
		cap5 = Capgauge(5, ni_config_file=capgauge_config, name='leg5')
		"""
		cap = CompositeCapgauge(range(6), capgauge_config)
		cap_dict = {'obj': cap, 
					'slope': 25,
					'piston': 0}

		cap_dict_0 = {'obj': cap,
				'slope': 25,
				'piston': 0,
				'index': 0
				}
		cap_dict_1 = {'obj': cap,
				'slope': 25,
				'piston': 0,
				'index': 1
				}
		cap_dict_2 = {'obj': cap,
				'slope': 25,
				'piston': 0,
				'index': 2
				}
		cap_dict_3 = {'obj': cap,
				'slope': 25,
				'piston': 0,
				'index': 3
				}
		cap_dict_4 = {'obj': cap,
				'slope': 25,
				'piston': 0,
				'index': 4
				}
		cap_dict_5 = {'obj': cap,
				'slope': 25,
				'piston': 0,
				'index': 5
				}
		pico_dict_0 = {'obj': picomotor1,
				'axis': 1,
		}
		pico_dict_1 = {'obj': picomotor1,
				'axis': 2,
		}
		pico_dict_2 = {'obj': picomotor1,
				'axis': 3,
		}
		pico_dict_3 = {'obj': picomotor1,
				'axis': 4,
		}
		pico_dict_4 = {'obj': picomotor2,
				'axis': 1,
		}
		pico_dict_5 = {'obj': picomotor2,
				'axis': 2,
		}

		#### CREATION of LEGS ###
		self.legs = [MotorLeg(cap_dict_0, pico_dict_0),
				MotorLeg(cap_dict_1, pico_dict_1),
				MotorLeg(cap_dict_2, pico_dict_2),
				MotorLeg(cap_dict_3, pico_dict_3),
				MotorLeg(cap_dict_4, pico_dict_4),
				MotorLeg(cap_dict_5, pico_dict_5),
		]

		####### NEW; TRY TO UTILIZE THE CompositeCapgauge #######
		self.compositeLegs = CompositeMotorLegs(cap_dict, 
							[pico_dict_0, pico_dict_1, pico_dict_2, pico_dict_3, pico_dict_4, pico_dict_5])

		#### Save the config file name
		self.calibrate_config = os.path.dirname(os.path.realpath(__file__)) + '/' + calibrate_config

		if os.path.exists(self.calibrate_config):		# read the config...
			config = ConfigParser.RawConfigParser()
			config.read(self.calibrate_config)
			for index in range(len(self.legs)):
				leg = 'leg%d' % index
				self.legs[index].slope['up'] = config.getfloat(leg, 'slope.up')
				self.legs[index].slope['down'] = config.getfloat(leg, 'slope.down')
		else:
			self.calibrate()

	def setMoveWidget(self, widget):
		"""
		@Purpose:
			Set a wx.Panel widget to attach to this actuator (for customized displaying).
		@Inputs:
			(wx.Panel) widget = input attaching widget.
		"""
		if widget != None:
			assert isinstance(widget, HexapodActuatorWxScrolledPanel), "widget is %s, but it's required to be HexapodActuatorWxScrolledPanel" % repr(type(widget))
		self.moveWidget = widget

	def calibrate(self):
		"""
		@Purpose:
			Calibrate the 6 motor legs. Figuring out the correlation between motor steps and capgauge position.
		"""
		# calibrate directional slopes
		for index in range(len(self.legs)):
			self.legs[index].calibratePositive()
			self.legs[index].calibrateNegative()

		# write the calibration to a config.
		config = ConfigParser.RawConfigParser()
		for index in range(len(self.legs)):
			leg = 'leg%d' % index
			config.add_section(leg)
			config.set(leg, 'slope.up', self.legs[index].slope['up'])
			config.set(leg, 'slope.down', self.legs[index].slope['down'])

		config_f = open(self.calibrate_config, 'w')
		config.write(config_f)
		config_f.close()

	def capgaugeChangeComposite(self, target_capgauge, min_amounts=[0.005, 0.005, 0.005, 0.005, 0.005, 0.005], max_iter=3):
		"""
		@Purpose:
			improved capgaugeChange function for utilizing CompositeCapgauge readings
		"""
		################################## Error handling #######################################
		if len(target_capgauge) != len(self.legs):
			raise HexaPodActuatorException("len(target_capgauge) != %d" % len(self.legs),
				"ERROR: target_capgauge definitions must be equal to length of leg numbers.")

		if len(min_amounts) != len(self.legs):
			raise HexaPodActuatorException("len(min_amounts) != %d" % len(self.legs),
				"ERROR: min_amounts definitions must be equal to length of leg numbers.")

		for i in range(len(min_amounts)):
			if type(min_amounts[i]) != int and type(min_amounts[i]) != float and \
					type(amounts[i]) != numpy.float64 and type(amounts[i]) != numpy.float32:
				raise HexaPodExcept('min_amounts[%d] != int and min_amounts[%d] != float' % (i, i),
					"ERROR: min_amounts must defined as INT or FLOAT.")
		###########################################################################################

		for i in range(max_iter):
			# update the movePanel plots, to re-scale every iterations
			if self.moveWidget != None:
				self.moveWidget.setAutoPlotCapYLim()
				self.moveWidget.plotCapChange()

			for index in range(len(self.legs)):
				curr_pos = self.legs[index].getPosition()
				delta_pos = target_capgauge[index] - curr_pos
				if abs(delta_pos) < min_amounts[index]:
					continue
				else:
					###### INTERRUPT FLAG #######
					if self.__stop__:
						self.__stop__ = False				# reset it, and exit
						return
					#############################
					self.legs[index].change(delta_pos)

					# update movePanel plots... if it's given.
					if self.moveWidget != None:
						after_pos = self.legs[index].getPosition()
						amounts_to_go = target_capgauge[index] - after_pos
						self.moveWidget.cap_change_amounts[index] = amounts_to_go
						curr_label = self.moveWidget.cap_change_labels[index].split(':')[0]
						self.moveWidget.cap_change_labels[index] = curr_label+':%d' % (i+1)
						self.moveWidget.plotCapChange()

		### finishing... stop the statusBar pulse ###
		if self.moveWidget != None:
			wx.PostEvent(self.moveWidget, ActuatorDoneEvent(fromFunction='capgaugeChange'))


	def capgaugeChange(self, target_capgauge, min_amounts=[0.005, 0.005, 0.005, 0.005, 0.005, 0.005], max_iter=3):
		"""
		@Purpose:
			Change the hex_pod six legs by amounts (in list)
			This method changes them in 6-legs sequence per iterations to achieve the goal change amounts.
				use the given starting positions to calculate the target positions
				leg1_iter1
				leg2_iter1
				...
				leg1_iter2
				leg2_iter2
				...
		@Inputs:
			(numpy.array) target_capgauge = [leg0_pos, leg1_pos, leg2_pos, leg3_pos, leg4_pos, leg5_pos]
			(numpy.array) amounts = [leg0, leg1, leg2, leg3, leg4, leg5]
			(list) min_amounts = minimum amount lists
			(int) max_iter = maximum iterations to perform
		"""
		################################## Error handling #######################################
		if len(target_capgauge) != len(self.legs):
			raise HexaPodActuatorException("len(target_capgauge) != %d" % len(self.legs),
				"ERROR: target_capgauge definitions must be equal to length of leg numbers.")

		if len(min_amounts) != len(self.legs):
			raise HexaPodActuatorException("len(min_amounts) != %d" % len(self.legs),
				"ERROR: min_amounts definitions must be equal to length of leg numbers.")

		for i in range(len(min_amounts)):
			if type(min_amounts[i]) != int and type(min_amounts[i]) != float and \
					type(amounts[i]) != numpy.float64 and type(amounts[i]) != numpy.float32:
				raise HexaPodExcept('min_amounts[%d] != int and min_amounts[%d] != float' % (i, i),
					"ERROR: min_amounts must defined as INT or FLOAT.")
		###########################################################################################

		for i in range(max_iter):
			# update the movePanel plots, to re-scale every iterations
			if self.moveWidget != None:
				self.moveWidget.setAutoPlotCapYLim()
				self.moveWidget.plotCapChange()

			for index in range(len(self.legs)):
				curr_pos = self.legs[index].getPosition()
				delta_pos = target_capgauge[index] - curr_pos
				if abs(delta_pos) < min_amounts[index]:
					continue
				else:
					###### INTERRUPT FLAG #######
					if self.__stop__:
						self.__stop__ = False				# reset it, and exit
						return
					#############################
					self.legs[index].change(delta_pos)

					# update movePanel plots... if it's given.
					if self.moveWidget != None:
						after_pos = self.legs[index].getPosition()
						amounts_to_go = target_capgauge[index] - after_pos
						self.moveWidget.cap_change_amounts[index] = amounts_to_go
						curr_label = self.moveWidget.cap_change_labels[index].split(':')[0]
						self.moveWidget.cap_change_labels[index] = curr_label+':%d' % (i+1)
						self.moveWidget.plotCapChange()

		### finishing... stop the statusBar pulse ###
		if self.moveWidget != None:
			wx.PostEvent(self.moveWidget, ActuatorDoneEvent(fromFunction='capgaugeChange'))

	def legChange(self, amounts, min_amounts=[0.005, 0.005, 0.005, 0.005, 0.005, 0.005], max_iter=3):
		"""
		@Purpose:
			Change ths hex_pod six legs by amounts (in list)
			This method changes the leg ONE BY ONE:
				leg1_change_iter1
				leg1_change_iter2
				leg2_change_iter1
				leg2_change_iter2
				...
		@Inputs:
			(list) amounts = [leg0, leg1, leg2, leg3, leg4, leg5]
			(list) min_amounts = minimum amount lists
			(int) max_iter = maximum iterations to perform
		"""
		dummy_delta = 999999

		################################## Error handling #######################################
		if len(amounts) != 6:
			raise HexaPodActuatorException("len(legs) != 6",
				"ERROR: Input legs changes requires 6 amounts.")
		if len(min_amounts) != 6:
			raise HexaPodActuatorException("len(min_amounts) != 6",
				"ERROR: min_amounts definitions must be length of 6.")

		for i in range(len(amounts)):
			if type(amounts[i]) != int and type(amounts[i]) != float and \
					type(amounts[i]) != numpy.float64 and type(amounts[i]) != numpy.float32:
				raise HexaPodActuatorException('type(amounts[%d]) == %s' % (i, str(type(amounts[i]))),
					"ERROR: Input legs positions must be INT or FLOAT.")

		for i in range(len(min_amounts)):
			if type(min_amounts[i]) != int and type(min_amounts[i]) != float and \
					type(amounts[i]) != numpy.float64 and type(amounts[i]) != numpy.float32:
				raise HexaPodExcept('min_amounts[%d] != int and min_amounts[%d] != float' % (i, i),
					"ERROR: min_amounts must defined as INT or FLOAT.")
		############################################################################################

		delta = [dummy_delta, dummy_delta, dummy_delta, dummy_delta, dummy_delta, dummy_delta]
		for index in range(len(self.legs)):
			for i in range(max_iter):
				if delta[index] < min_amounts[index]:
					continue
				prev_pos = self.legs[index].getPosition()

				### INTERRUPT FLAG ###
				if self.__stop__:
					self.__stop__ = False				# reset
					return
				######################
				self.legs[index].change(amounts[index])

				curr_pos = self.legs[index].getPosition()
				delta[index] = abs(curr_pos - prev_pos)
				if amounts[index] > 0:
					amounts[index] -= delta[index]
				else:
					amounts[index] += delta[index]
				
				# update movePanel plots... if it's given.
				if self.moveWidget != None:
					self.moveWidget.leg_change_amounts[index] = amounts[index]
					curr_label = self.moveWidget.leg_change_labels[index].split(':')[0]
					self.moveWidget.leg_change_labels[index] = curr_label+':%d' % (i+1)
					self.moveWidget.plotLegChange()
					self.moveWidget.plotCapChange()

		### finishing... stop the statusBar pulse ###
		if self.moveWidget != None:
			wx.PostEvent(self.moveWidget, ActuatorDoneEvent(fromFunction='legChange'))

	def change(self, cap_change_amounts, leg_change_amounts):
		"""
		@Purpose: (DEPRECATED)
			General change function that perform the leg changes.
		@Inputs:
			(list) change_amounts = amounts to change
		"""
		starting_capgauge = self.getPositions()
		self.legChange(leg_change_amounts)
		self.capgaugeChange(starting_capgauge, cap_change_amounts)

	def stop(self):
		"""
		@Purpose:
			STOP 'legChange' function call or 'capChange' function call by setting private flag that's checked in the functions
		"""
		for motor in self.picomotors:
			motor.abortMotion()
		self.__stop__ = True

	def getPositions(self):
		"""
		@Purpose:
			get positions for six legs
		@Output:
			(numpy.array) [leg0, leg1, leg2, leg3, leg4, leg5]
		"""
		if not self.__isCompositeCapgauge__:
			retlist = []
			for index in range(len(self.legs)):
				retlist.append(self.legs[index].getPosition())

			return numpy.array(retlist)
		else:
			slope = self.legs[0].capgauge['slope']
			piston = self.legs[0].capgauge['piston']
			cap = self.legs[0].capgauge['obj']
			return numpy.array(cap.readPositions(slope, piston))
