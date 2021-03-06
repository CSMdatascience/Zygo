# Module provides the WEX server for RTD data


import asyncore, socket
import omMeas.wexLib.asynSched as asynSched
import omMeas.wexLib.wsp as wsp
import omMeas.wexLib.nio as nio
import time
import os

import logging

import Config
import Probes
import omMeas.wexLib.Device as Device
import SensorCache

#DEBUG = __name__ == "__main__"
DEBUG = True

#======================================================================#

def trace(msg, printNewLine = True):
    if DEBUG:
        if printNewLine:
            print msg
        else:
            print msg,

#=====================================================================#

    #This routine has been ported from a routine supplied by Zygo?

def calcAirIndex (curTemp, curPres, curHumi):
    """
    ATMOSPHERE_CORRECT()
    This function is passed the IC number for vacuum for whatever DMI
    is initialized and returns the corrected IC after taking into
    account the atmospheric conditions - Barometric Pressure (mm Hg),
    Temperature (deg C) and Relative Humidity (Percentage)

    This function calculates the index of air (N).

    Refer to Zygo ZMI-1000 manual for calculation documentation
    """
    if curTemp == None or curPres == None or curHumi == None:
        return None

    f_term1 = 4.07859739    #some magic values supplied by Zygo
    f_term2 = 0.44301857
    f_term3 = 0.00232093
    f_term4 = 0.00045785

    t_sqr = float(curTemp) * float(curTemp)
    t_cube = t_sqr * float(curTemp)

    f = (curHumi/100.0)*(f_term1 +f_term2*curTemp +f_term3*t_sqr
                                            +f_term4*t_cube)
   
    n1 = 1.0 + (curPres*(0.817 -(0.0133*curTemp))*0.000001)
    n1 = n1/(1 +0.003661*curTemp)
    n1 = n1*(0.00000038369*curPres) +1
    n1 = n1 -(0.00000005607943*f)
    return n1

#======================================================================#

def createParamLine(prefix, format = None, value = None):
    if value != None:
        s = prefix +format%value
    else:
        s = prefix +"n/a"
    return wsp.ParameterLine(s)

#======================================================================#

class rtdWexServer(asyncore.dispatcher):
    def __init__(self, asch, serverPort=6217, probeMap=dict()):
        asyncore.dispatcher.__init__(self, None, asch.sockMap)
        self.asch = asch    # asynScheduler

        self.serverPort = serverPort
        self.probeMap = probeMap

        self.startListen()

#----------------------------------------------------------------------#

    def startListen(self):
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
            # a little asyncore magic to prevent the "Address already
            #   in use" error (WSAEADDRINUSE/EADDRINUSE)
        self.set_reuse_addr()
        serverHost = ""
        self.bind((serverHost, self.serverPort))
        print "RTDWEX: Listening on %s:%d" % (serverHost,
                                                     self.serverPort)
        logging.info ("RTDWEX: Listening on %s:%d" % (serverHost,
                                                     self.serverPort))
        self.listen(5)

#----------------------------------------------------------------------#

    def handle_accept(self):
        print "try accept..."
        cliSock, cliAddr = self.accept()
        print "accepted connection: %s:%s" % (cliAddr[0], cliAddr[1])
        logging.info ("accepted connection: %s:%s" % (cliAddr[0],
                                                        cliAddr[1]))
        cliSess = rtdWexSession(cliSock, cliAddr, self.asch,
                                                        self.probeMap)
    
#----------------------------------------------------------------------#

    def writable(self):
        return(False)

#----------------------------------------------------------------------#

    def handle_read(self):
        # required as side-effect of wanting accept notifications
        pass

#----------------------------------------------------------------------#

    def handle_connect(self):
        # side-effect of doing accept?
        pass

#======================================================================#

class rtdWexSession(asynSched.asynStream):
    def __init__(self, cliSock, cliAddr, asch, probeMap):
        asynSched.asynStream.__init__(self, asch, cliSock, 8000)
        self.cliAddr = cliAddr
        self.probeMap = probeMap

#----------------------------------------------------------------------#

    def fatalProto(self,msg):
        print "Fatal error in protocol: %s" % msg
        logging.warning ("Fatal error in protocol: %s" % msg)
        self.close()
        # TBD: how do we delete ourselves?

#----------------------------------------------------------------------#

    def onReadTemp(self, reqPkt):
        isError = False
        rspParams = []
        sensorParams = reqPkt.getParamByName("Sensor")

        for param in sensorParams:
            sensorName = param.getValue()
            trace ("Got query for sensor %s" % sensorName)
            niBoxProbeName=self.probeMap.get(sensorName.lower())
            if niBoxProbeName == None:
                niBoxProbeName = sensorName
            sensorEnt = SensorCache.findSensor ("T." +niBoxProbeName)
            if sensorEnt is None:   # if not found
                isError = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                                        +sensorName, "No such sensor"))
                trace ("Cannot find %s in Cache" % niBoxProbeName)
            elif sensorEnt[3]:      # if an error
                paramName = "ErrorDesc." +sensorName
                rspParams.append (wsp.ParameterLine (paramName,
                                                        sensorEnt[0]))
            else:
                paramName = "Sensor." +sensorName
                paramValue = (str(sensorEnt[0]) + ' '
                                    +str(time.time() -sensorEnt[1]))
                rspParams.append (wsp.ParameterLine (paramName,
                                                            paramValue))
        return (isError, rspParams)

#----------------------------------------------------------------------#

    def onCalibrate(self, reqPkt):
            # isError and currentSection must be inside a multible
            # object otherwise helperFcn can't modify them. :-(
            # "Code in a nested function's body may access (BUT NOT
            # REBIND) local variables of an outer function..."
        isError = [False]
        currentSection = [None]
        rspParams = []

            # create empty configParser object
        import ConfigParser
        config = ConfigParser.RawConfigParser()

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -#

            # helper function that is called for each line from the
            # ni box
        def helperFcn(line):
            line = line.lstrip()
            if isError[0] or line[0] in "#;":
                return
            elif line[0] == '[':
                if line[-1] != ']':
                    isError[0] = True
                    rspParams.append (wsp.ParameterLine ("ErrorDesc",
                        "Unable to parse nibox's ini file: %s" % line))
                    trace ("Unable to parse nibox's ini file: %s" %line) 
                else:
                    currentSection[0] = line [1:-1]
                    trace ("Current section: %s" % currentSection [0]) 
                    try:
                        config.add_section (currentSection[0])
                    except ConfigParser.DuplicateSectionError:
                        isError[0] = True
                        rspParams.append (wsp.ParameterLine("ErrorDesc",
                                    "Unable to parse nibox's ini file: "
                                    "Duplicate Section Error"))
                        trace ("Unable to parse nibox's ini file: "
                                            "Duplicate Section Error") 
            else:
                if currentSection[0] == None:
                    isError[0] = True
                    rspParams.append (wsp.ParameterLine("ErrorDesc",
                                    "Unable to parse nibox's ini file: "
                                    "Missing Section Error"))
                    trace ("Unable to parse nibox's ini file: "
                                                "Missing Section Error")
                pos = line.find(':')
                pos1 = line.find('=')
                if pos == -1 or pos > pos1:
                    pos = pos1
                if pos <= 0:
                    isError[0] = True
                    rspParams.append (wsp.ParameterLine ("ErrorDesc"
                        "Unable to parse nibox's ini file: %s" % line))
                    trace ("Unable to parse nibox's ini file: %s" %line) 
                else:
                    option = line [:pos]
                    if pos == len(line) -1:
                        value = ""
                    else:
                        value = line [pos+1:]
                    try:
                        config.set (currentSection[0], option, value) 
                    except ConfigParser.NoSectionError:
                        isError[0] = True
                        rspParams.append (wsp.ParameterLine("ErrorDesc",
                                    "Unable to parse nibox's ini file: "
                                    "No Section Error"))
                        trace ("Unable to parse nibox's ini file: "
                                                    "No Section Error") 
            pass

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -#

           # get niBox address
        sensorParams = reqPkt.getParamByName("Sensor")
        if len(sensorParams) == 0:
            isError[0] = True
            rspParams.append (wsp.ParameterLine("ErrorDesc",
                                        "No Sensors in request packet"))
            trace ("No Sensors in request packet") 
            return (isError[0], rspParams)
        sensorName = sensorParams [0].getValue()
        niBoxInfo = Config.getNiBoxInfo()
        for name in niBoxInfo.keys():
            niBoxProbeName=self.probeMap.get(sensorName.lower())
            if niBoxProbeName == None:
                niBoxProbeName = sensorName
            if niBoxProbeName.startswith(name):
                niBoxName = name
                break;
        else:
            isError[0] = True
            rspParams.append (wsp.ParameterLine("ErrorDesc",
                            "Cannot find nibox for %s" % sensorName))
            trace ("Cannot find nibox for %s" % sensorName) 
            return (isError[0], rspParams)

            # open ftp connection & login
        from ftplib import FTP, error_perm, error_temp
        try:
            ftp = FTP (niBoxInfo [niBoxName][0])
            rsp = ftp.login()
            trace ("login returns %s" % str(rsp))
        except (IOError, error_perm, error_temp), msg:
            isError[0] = True
            rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                    "Cannot login to %s" % niBoxName))
            trace ("Cannot login to %s" % niBoxName)
            return (isError[0], rspParams)

            # ftp get ini file, parsing each line into a configParser
        niBoxMasterDir  = niBoxInfo [niBoxName][2]  # e.g. local C:/spam
        niBoxMasterFile = niBoxInfo [niBoxName][3]  # e.g. eggs.INI
        niBoxBackupFile = niBoxInfo [niBoxName][4]  # e.g. eggs.OLD
        niBoxTargetDir  = niBoxInfo [niBoxName][5]  # e.g. NI-RT
        niBoxTargetFile = niBoxInfo [niBoxName][6]  # eg tmp_Mon_cfg.INI
        if niBoxMasterDir in [None, ""]:
            niBoxMasterDir = "remote NI-RT"
        if niBoxMasterFile in [None, ""]:
            niBoxMasterFile = "tmp_Mon_cfg.INI"
        if niBoxTargetDir in [None, ""]:
            niBoxTargetDir = "NI-RT"
        if niBoxTargetFile in [None, ""]:
            niBoxTargetFile = "tmp_Mon_cfg.INI"

        tokens = niBoxMasterDir.split(' ', 1)
        if tokens [0].lower() == "remote":
            masterFilename = tokens [1] +'/' +niBoxMasterFile
            if niBoxTargetDir in [None, ""]:
                backupFilename = None
            else:
                backupFilename = tokens [1] +'/' +niBoxBackupFile
            rebootFilename = tokens [1] +"/reboot.txt"
            try:
                rsp = ftp.retrlines ("RETR %s" % masterFilename,
                                                            helperFcn)
                trace ("retrlines returns %s" % str(rsp))
            except (IOError, error_perm, error_temp), msg:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                                "Cannot read ini file"))
                trace ("Cannot read ini file")
                return (isError[0], rspParams)
            masterIsLocal = False
        elif tokens [0].lower() == "local":
            masterFilename = tokens [1] +os.sep +os.sep +niBoxMasterFile
            if niBoxTargetDir in [None, ""]:
                backupFilename = None
            else:
                backupFilename =tokens[1]+os.sep+os.sep +niBoxBackupFile
            rebootFilename = niBoxTargetDir +"/reboot.txt"
            try:
                filesRead = config.read (masterFilename)
            except ConfigParser.ParsingError, err:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                            "Cannot process ini file"))
                trace ("Cannot process ini file")
                return (isError[0], rspParams)
            if not filesRead:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                                "Cannot read ini file"))
                trace ("Cannot read ini file")
                return (isError[0], rspParams)
            masterIsLocal = True
        else:
            isError[0] = True
            rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                                "Cannot find ini file"))
            trace ("Cannot find ini file")
            return (isError[0], rspParams)

            # get/read currentTemperature
        currentTempParams=reqPkt.getParamByName("CalibrationTemperature")
        if len(currentTempParams) > 1:
            isError[0] = True
            rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                    "Too may calibration temperatures"))
            trace ("Too may calibration temperatures")
        elif len(currentTempParams) == 1:
            try:
                currentTemp = float(currentTempParams [0].getValue())
            except ValueError:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc",
                            "Illegal calibration temperature value"))
                trace ("Illegal calibration temperature value")
        elif Config.getThermometer() == None:
            isError[0] = True
            rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                        "No calibration temperature"))
            trace ("No calibration temperature")
        else:
            try:
                currentTemp = Config.getThermometer().getValue()
            except Probes.ProbeError:
                try:
                    currentTemp = Config.getThermometer().getValue()
                except Probes.ProbeError:
                    isError[0] = True
                    rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                "Unable to read precision thermometer"))
                    trace ("Unable to read precision thermometer")
        if not isError[0] and not (15 < currentTemp < 30):
            isError[0] = True
            rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                        "Calibration temperature is "
                                        "outside a reasonable range"))
            trace ("Calibration temperature is outside a reasonable "
                                                                "range")
        if isError[0]:
            return (isError[0], rspParams)
        trace ("  calibration temperature is: %f" % currentTemp)

        calHistorySection = "CALIBRATION HISTORY"
        if not config.has_section (calHistorySection):
            config.add_section(calHistorySection)
        nowInt = int(time.time())

        setupInfoSection = "SETUP INFO"
        if not config.has_section (setupInfoSection):
            config.add_section(setupInfoSection)
        if config.has_option (setupInfoSection, "CalSerial"):
            oldCalSerial = config.get (setupInfoSection, "CalSerial")
        else:
            oldCalSerial = None
        config.set (setupInfoSection, "CalSerial", str (-nowInt))

            # for each sensor in packet
            #     calc new delta from currentTemperature, sensor value
            #            & old delta
            #     reset delta in ini file
            #     set rspParams as we go
            #     add entry to calibration history
        for param in reqPkt.getParamByName("Sensor"):
            sensorName = param.getValue ()
            niBoxProbeName=self.probeMap.get(sensorName.lower())
            if niBoxProbeName == None:
                niBoxProbeName=sensorName
            sensorEnt = SensorCache.findSensor ("T." +niBoxProbeName)
            if sensorEnt is None:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                                        +sensorName, "No such sensor"))
                trace ("No such sensor: %s" % sensorName)
                continue
            elif sensorEnt[3]:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                                        +sensorName, sensorEnt[0]))
                continue
            if sensorEnt[2] not in (None, oldCalSerial):
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                    +sensorName, "Calibration timestamp not current"))
                trace ("Calibration timestamp not current: %s" %
                                                            sensorName)
                continue
            try:
                sensorValue = float(sensorEnt[0])
            except ValueError, err:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                            +sensorName, "Cannot calibrate sensor"))
                trace ("Cannot calibrate sensor: %s" % sensorName)
                continue
            tokens = niBoxProbeName.split('.')
            section = "MULTIPLEXER%s_SETTINGS" % tokens [-2]
            option = "CH%s_SETTINGS" % tokens [-1]
            calHistoryOption = "mux%s.cal%s.%s" % (tokens [-2],
                                                tokens[-1], str(nowInt))

            try:
                s = config.get(section,option)
            except ConfigParser.Error, err:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                            +sensorName, "Cannot find nibox parameter"))
                trace ("Cannot find nibox parameter: %s" % sensorName)
                continue
            if s == None:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                            +sensorName, "Cannot find nibox parameter"))
                trace ("Cannot find nibox parameter: %s " %sensorName)
                continue
            tokens = s.strip('"').split(',')
            trace ("getting %s/%s: %s" % (section, option, s))
            try:
                oldDelta = float (tokens [-1])
            except (ValueError, IndexError):
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                            +sensorName, "Bad ini value for sensor"))
                trace ("Bad ini value for sensor: %s"%sensorName)
                continue
            calHistoryValue = "%s,%s"%(tokens [-2],tokens [-1])
            newDelta = oldDelta +currentTemp -sensorValue
            if not (-1.0 <= newDelta <= 1.0):
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                        +sensorName, "New sensor offset out of range"))
                trace ("New sensor offset out of range: %s"%sensorName)
                continue
            tokens [-1] = str (newDelta)
            calHistoryValue = (calHistoryValue +
                                    ",%s,%s"%(tokens [-2],tokens [-1]))
            try:
                config.set (section, option, '"' +','.join(tokens) +'"')
            except ConfigParser.Error, err:
                # should never happen since the get worked.
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                            +sensorName, "Cannot set nibox parameter"))
                trace ("Cannot set nibox parameter: %s" % sensorName)
                continue
            trace ("setting %s/%s: %s" % (section, option,
                                            '"' +','.join(tokens) +'"'))
            paramName = "NewCalibration." +sensorName
            paramValue= str (newDelta)
            rspParams.append (wsp.ParameterLine (paramName, paramValue))
            try:
                config.set (calHistorySection, calHistoryOption,
                                                        calHistoryValue)
            except ConfigParser.Error, err:
                    # should never happen since we already created the
                    #   calHistorySection.
                pass

        if isError[0]:
            return (isError[0], rspParams)

        if masterIsLocal:
                # remove old backup file
                # rename current name to backup name
                # (we don't care if the delete or the rename fails so
                # catch and ignore any os errors here.)
            if backupFilename != None:
                try:
                    os.unlink (backupFilename)
                except (OSError, IOError), msg:
                    trace ("unlink(%s) threw %s" % (backupFilename,
                                                        str(msg)))

                try:
                    os.rename(masterFilename, backupFilename)
                except (OSError, IOError),  msg:
                    trace ("rename(%s,%s) threw %s" % (masterFilename,
                                            backupFilename, str(msg)))
            else:
                try:
                    os.unlink (masterFilename)
                except (OSError, IOError), msg:
                    trace ("unlink(%s) threw %s" % (masterFilename,
                                                            str(msg)))

                # save new config file as a tmp file in config dir
            try:
                tmpFile = open (masterFilename, 'w+')
                tmpFile.write ("# some sensors calibration on %s\n" %
                                                        time.asctime ())
                config.write (tmpFile)
                tmpFile.flush()
                tmpFile.seek(0)
            except IOError, msg:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                            +sensorName, "Unable to open new ini file"))
                trace ("Unable to open new ini file")
                return (isError[0], rspParams)

                # ftp file to remote system
            try:
                rsp = ftp.storlines ("STOR %s" % niBoxTargetDir +'/'
                                            +niBoxTargetFile, tmpFile)
                trace ("storlines(%s) returns %s" % (niBoxTargetDir +'/'
                                            +niBoxTargetFile, str(rsp)))
            except (IOError, error_perm, error_temp), msg:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                            "Cannot write ini file"))
                trace ("Cannot write ini file: %s" % str(msg))
                try:    #roll back the rename
                    os.rename(backupFilename, masterFilename)
                except (OSError, IOError),  msg:
                    trace ("rename threw %s" % str(msg))
                return (isError[0], rspParams)
            if DEBUG:
                try:
                    rsp = ftp.retrlines ("RETR %s" % niBoxTargetDir +'/'
                                            +niBoxTargetFile)
                    trace ("retrlines(%s) returns %s" % (niBoxTargetDir
                                    +'/' +niBoxTargetFile, str(rsp)))

                except (IOError, error_perm, error_temp), msg:
                    trace ("Cannot verify ini file")
        else:
                # save new config file locally
            trace ("Outputting new ini file")
            try:
                tmpFile = os.tmpfile ()
                tmpFile.write ("# some sensors calibration on %s\n" %
                                                        time.asctime ())
                config.write (tmpFile)
                tmpFile.seek(0)
            except IOError, msg:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc."
                            +sensorName, "Unable to open new ini file"))
                trace ("Unable to open new ini file")
                return (isError[0], rspParams)


                # ftp remove old backup file
                # ftp rename current name to backup name
                # (we don't care if the delete or the rename fails so
                # catch and ignore any ftp errors here.)
            if backupFilename != None:
                try:
                    rsp = ftp.delete(backupFilename)
                    trace ("delete returns %s" % str(rsp))
                except (error_perm, error_temp),  msg:
                    trace ("delete threw %s" % str(msg))

                try:
                    rsp = ftp.rename(masterFilename, backupFilename)
                    trace ("rename returns %s" % str(rsp))
                except (error_perm, error_temp),  msg:
                    trace ("rename threw %s" % str(msg))
            else:
                try:
                    rsp = ftp.delete(masterFilename)
                    trace ("delete returns %s" % str(rsp))
                except (error_perm, error_temp),  msg:
                    trace ("delete threw %s" % str(msg))

                # ftp new config file to remote system
            try:
                rsp = ftp.storlines ("STOR %s" % masterFilename,tmpFile)
                trace ("storlines returns %s" % str(rsp))
            except (IOError, error_perm, error_temp), msg:
                isError[0] = True
                rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                            "Cannot write ini file"))
                trace ("Cannot write ini file: %s" % str(msg))
                if backupFilename != None:
                    try:    #roll back the rename
                        rsp = ftp.rename(backupFilename, masterFilename)
                        trace ("rename returns %s" % str(rsp))
                    except (error_perm, error_temp),  msg:
                        trace ("rename threw %s" % str(msg))
                return (isError[0], rspParams)
            if DEBUG:
                try:
                    rsp = ftp.retrlines ("RETR %s" % masterFilename)
                    trace ("retrlines returns %s" % str(rsp))
                except (IOError, error_perm, error_temp), msg:
                    trace ("Cannot verify ini file")

        tmpFile.close()
            # ftp put a "reboot" file
        try:
            tmpFile = os.tmpfile()
            tmpFile.write ("The existance of this file on the nibox "
                "means the nibox needs to reread it's config ini file")
            tmpFile.seek (0)
            rsp = ftp.storlines ("STOR %s" % rebootFilename, tmpFile)
            trace ("storlines returns %s" % str(rsp))
        except (OSError, IOError, error_perm, error_temp), msg:
            isError[0] = True
            rspParams.append (wsp.ParameterLine ("ErrorDesc",
                                        "Cannot write the reboot file"))
            trace ("Cannot write the reboot file: %s" % str(msg))

        rsp = ftp.close()
        trace ("close returns %s" % str(rsp))
        return (isError[0], rspParams)

#----------------------------------------------------------------------#

    def onGetSensors(self, reqPkt):
        isError = False
        rspParams = []
        for key in self.probeMap.keys():
            niBoxProbeName=self.probeMap.get(key.lower())
            if niBoxProbeName == None:
                isError = True
                rspParams.append(wsp.ParameterLine( "ErrorDesc." +key,
                                                    "No such sensor"))
                trace ("Cannot find %s in %s" %(key,str(self.probeMap)))
            else:
                sensorEnt = SensorCache.findSensor("T." +niBoxProbeName)
                if sensorEnt is None:
                    isError = True
                    rspParams.append(wsp.ParameterLine( "ErrorDesc."
                                                +key, "No such sensor"))
                    trace ("Cannot find %s in Cache" % niBoxProbeName)
                elif sensorEnt[3]:
                    isError = True
                    rspParams.append(wsp.ParameterLine( "ErrorDesc."
                                                    +key, sensorEnt[0]))
                else:
                    paramValue = (str(sensorEnt[0]) + ' '
                                        +str(time.time() -sensorEnt[1])
                                        + ' ' +str (sensorEnt[2]))
                    rspParams.append (wsp.ParameterLine (key,
                                                            paramValue))
        return (isError, rspParams)

#----------------------------------------------------------------------#

    def onGetCache(self, reqPkt):
        isError = False
        rspParams = []
        for key in SensorCache.getKeys():
            sensorEnt = SensorCache.findSensor(key)
            if sensorEnt is None:       # this should never happen
                isError = True
                rspParams.append( wsp.ParameterLine( "ErrorDesc."
                                +key.capitalize(), "No such sensor"))
                trace ("Cannot find %s in Cache" % key)
            elif sensorEnt[3]:
                isError = True
                rspParams.append(wsp.ParameterLine( "ErrorDesc."
                                    +key.capitalize(), sensorEnt[0]))
            else:
                paramName = key.capitalize()
                paramValue = (str(sensorEnt[0]) + ' '
                                        +str(time.time() -sensorEnt[1])
                                        + ' ' +str (sensorEnt[2]))
                rspParams.append (wsp.ParameterLine (paramName,
                                                            paramValue))
        return (isError, rspParams)

#----------------------------------------------------------------------#

    def onGetAllWeather(self, reqPkt):
        isError = False
        rspParams = []
        for key in SensorCache.getKeys():
            sensorEnt = SensorCache.findSensor(key)
            if sensorEnt is None:       # this should never happen
                isError = True
                rspParams.append( wsp.ParameterLine( "ErrorDesc."
                                +key.capitalize(), "No such sensor"))
                trace ("Cannot find %s in Cache" % key)
            elif sensorEnt[3]:
                isError = True
                rspParams.append(wsp.ParameterLine( "ErrorDesc."
                                    +key.capitalize(), sensorEnt[0]))
            else:
                paramName = key.capitalize()
                paramValue = str(sensorEnt[0])
                rspParams.append (wsp.ParameterLine (paramName,
                                                            paramValue))
        return (isError, rspParams)

#----------------------------------------------------------------------#

    def onReadWeather(self, reqPkt):
        isError = False
        rspParams = []
        stationParamList = reqPkt.getParamByName("StationName")
        if stationParamList == None:
            rspParams = [wsp.ParameterLine( "ErrorDesc",
                                        "Cannot find StationName")]
            print (" ** No station name found")
            return (True, rspParams)

        stationName = stationParamList[0].getValue().capitalize()
        if Config.getStations().has_key(stationName):
            station = Config.getStations() [stationName]
            print (station)
        else:
            print " ** Cannot find %s in %s" % (stationName,
                                                Config.getStations())
            rspParams = [wsp.ParameterLine( "ErrorDesc",
                            "Unknown station: %s" % stationName)]
            return (True, rspParams)

        curTemp = curPres = curHumi = airIndex = None
        try:
            curTemp = station.getTemperature()
            if (curTemp == None):
                paramLine=wsp.ParameterLine("ErrorDesc.Temperature",
                                                    "no sensor data")
                isError = True
            else:
                paramLine=createParamLine(" Temperature=", "%.3f",
                                                            curTemp)
        except Probes.ProbeError, err:
            paramLine = wsp.ParameterLine("ErrorDesc.Temperature",
                                                        err.strerror)
            isError = True
        rspParams.append (paramLine)
        try:
            curPres = station.getPressure()
            if (curPres == None):
                paramLine=wsp.ParameterLine("ErrorDesc.Pressure",
                                                    "no sensor data")
                isError = True
            else:
                paramLine = createParamLine(" Pressure=", "%.3f",
                                                            curPres)
        except Probes.ProbeError, err:
            paramLine = wsp.ParameterLine("ErrorDesc.Pressure",
                                                        err.strerror)
            isError = True
        rspParams.append (paramLine)
        try:
            curHumi = station.getHumidity()
            if (curHumi == None):
                paramLine=wsp.ParameterLine("ErrorDesc.RelativeHumidity",
                                                    "no sensor data")
                isError = True
            else:
                paramLine=createParamLine(" RelativeHumidity=", "%.1f",
                                                            curHumi)
        except Probes.ProbeError, err:
            paramLine = wsp.ParameterLine("ErrorDesc.RelativeHumidity",
                                                        err.strerror)
            isError = True
        rspParams.append (paramLine)
        airQuality = 0.9876
        paramLine = createParamLine(" AirQuality=", "%.4f", airQuality)
        rspParams.append (paramLine)
        try:
            airIndex = calcAirIndex (curTemp, curPres, curHumi)
            if (airIndex == None):
                paramLine=wsp.ParameterLine(" ErrorDesc="
                                    "Unable to calculate Air Index")
                isError = True
            else:
                paramLine = createParamLine(" AirIndex=", "%.14f",
                                                            airIndex)
        except Probes.ProbeError, err:
            paramLine = wsp.ParameterLine("ErrorDesc.AirIndex",
                                                        err.strerror)
            isError = True
        rspParams.append (paramLine)
        paramLine = createParamLine(" WeatherAge=", "%f",
                                                station.getMaxAge())
        rspParams.append (paramLine)

        return (isError, rspParams)

#----------------------------------------------------------------------#

    def onIdentify(self, reqPkt):
        isError = False
        rspParams = [wsp.ParameterLine(" ServerModel=23.45"),
                     wsp.ParameterLine(" ServerVersion=0.0"),
                     wsp.ParameterLine(" ServerConfig=Spam&Eggs")]
        for (key, device) in Config.mensorBarometer.items():
            try:
                barometerData = device.getUnitInfo()
                if barometerData is not None:
                    for (key1, item1) in barometerData.items():
                        rspParams.append (wsp.ParameterLine(
                                        "barometer.%s.%s" %(key, key1),
                                        str(item1)))
            except Device.DeviceError:
                pass
        return (isError, rspParams)

#----------------------------------------------------------------------#

    def procReqToRsp(self, reqPkt):
        isError = False
        if wsp.ReqPacket.getMagicPacketType() != reqPkt.getPacketType():
            rspParams = [wsp.ParameterLine( "ErrorDesc",
                                                    "Not a ReqPacket")]
            trace ("Not a ReqPacket")
            return wsp.RspPacket(reqPkt.getCtag(), wsp.ERROR, rspParams)

        try:
            commandName = reqPkt.getCmdName()
        except AttributeError:
            rspParams = [wsp.ParameterLine( "ErrorDesc",
                            "Unable to get ReqPacket command name")]
            trace ("Unable to get ReqPacket command name")
            return wsp.RspPacket(reqPkt.getCtag(), wsp.ERROR, rspParams)

        rspParams = []
        if commandName == wsp.READ_TEMPERATURE:
            isError, rspParams = self.onReadTemp (reqPkt)

        elif commandName == "Calibrate":
            isError, rspParams = self.onCalibrate (reqPkt)

        elif commandName == "GetSensors":
            isError, rspParams = self.onGetSensors (reqPkt)

        elif commandName == "GetCache":
            isError, rspParams = self.onGetCache (reqPkt)

        elif commandName == "ClearCache":
            SensorCache.clearCache()

        elif commandName == "GetAllWeather":
            isError, rspParams = self.onGetAllWeather (reqPkt)

        elif commandName in [wsp.MEASURE_WEATHER, wsp.READ_WEATHER]:
            isError, rspParams = self.onReadWeather (reqPkt)

        elif commandName == wsp.IDENTIFY:
            isError, rspParams = self.onIdentify (reqPkt)

        else:
            isError = True
            rspParams = [wsp.ParameterLine( "ErrorDesc",
                                "Unknown request: %s" % commandName)]
            trace ("Unknown request: %s" % commandName)


        if isError:
            rspKind = wsp.ERROR
        else:
            rspKind = wsp.COMPLETE
        return wsp.RspPacket(reqPkt.getCtag(), rspKind, rspParams)
            
#----------------------------------------------------------------------#

    def procRxOne(self):
        self.rxbuf = self.rxbuf.replace("\r", "\n")
        pktLen = self.rxbuf.find("\n.\n")
        if ( pktLen < 0 ):
            print "--no pktterm fnd (len=%d)" % len(self.rxbuf)
            return(0)
        pktLen += 2 # skip to dot
        pktStr = self.rxbuf[0:pktLen]
        print "Read: %s" % pktStr
        self.rxbuf = self.rxbuf[pktLen:]
        try:
            reqPkt = wsp.PacketFactory.createPacket(pktStr)
        except nio.ParseError, x:
            print "Parse error: %s" % str(x)
            return(0)
        rspPkt = self.procReqToRsp(reqPkt)
        if rspPkt is None:
            return 1    # XXX; this should go away
        print "sending response packet..."
        rspStr = str(rspPkt)
        print "%s" % rspStr
        self.txbuf += rspStr
        print "response packet len = %d" % len(rspStr)
        return(1)

#======================================================================#

if __name__ == "__main__":
    currentSection = None
    INI_FILENAME = "NI-RT/tmp_Mon_cfg.INI"
    isError = False
    print "running..."

        # create empty configParser object
    import ConfigParser
    config = ConfigParser.RawConfigParser()

        # helper function that is called for each line from the
        # ni box
    def helperFcn(line):
        global currentSection, config, isError
        line = line.lstrip()
        if isError:
            print "Error!"
        if line[0] in "#;":
            pass
        elif line[0] == '[':
            if line[-1] != ']':
                isError = True
                print "Unable to parse nibox's ini file: %s" % line
            else:
                currentSection = line [1:-1]
                try:
                    config.add_section (currentSection)
                except ConfigParser.DuplicateSectionError:
                    isError = True
                    print ("Unable to parse nibox's ini file: "
                                            "Duplicate Section Error")
        else:
            pos = line.find(':')
            pos1 = line.find('=')
            if pos == -1 or pos > pos1:
                pos = pos1
            if pos == -1:
                isError = True
                print "Unable to parse nibox's ini file: %s" % line
            else:
                option = line [:pos]
                if pos == len(line) -1:
                    value = ""
                else:
                    value = line [pos+1:]
                try:
                    config.set (currentSection, option, value) 
                except ConfigParser.NoSectionError:
                    isError = True
                    print ("Unable to parse nibox's ini file: "
                                                    "No Section Error")
        pass

        # open ftp connection & login
    from ftplib import FTP
    ftp = FTP ("rotr1tmp")
    ftp.login()
        # ftp get ini file, parsing each line into a configParser
        #   (use lambda expression for <helperCallback> or a 
        #   function defined inside onCalibrate)
    ftp.retrlines ("RETR %s" % INI_FILENAME, helperFcn)

#    for section in config.sections():
#        print
#        print "[%s]" % section
#        for option in config.options(section):
#            print "%s=%s" % (option, config.get( section, option))


    print "attempting to write file"
            # output new ini file
    try:
        tmpFile = open ("deleteMe.INI", 'w+')
        config.write (tmpFile)
        tmpFile.seek(0)
    except IOError:
        isError = True
        print "Cannot write local copy of ini file"

    print "attempting to ftp store file"
        # ftp put new ini file
    if not isError:
        ftp.storlines ("STOR %s" % "NI-RT/deleteMe.INI", tmpFile)
    else:
        print "Error prevents remote save of file"
#    while 1:
#        buf = tmpFile.readline()
#        if not buf: break
#        print buf,

    ftp.close()
