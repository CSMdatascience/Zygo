#! !/usr/bin/env python
# file: omMeas/rtdServer/rtdServer.py

"""
This implements the rtd server.
"""

# original author: kw
# rewrite author: glc

#=====================================================================#

import datetime
import omMeas.wexLib.asynSched as asynSched
import niboxProto
import rtdWex
import Config
#import Station
import ProbePoller

import logging

#=====================================================================#
today_str = datetime.datetime.today().strftime('%Y-%m-%d')

logFilename = "log/rtdServer_%s.log" % today_str
configFilename = "rtdConfig.ini"
configDirectory = "."
debugMode = False

#=====================================================================#

def RunApp():
    import sys, os
    global configFilename, logFilename, configDirectory, debugMode
    for i in range (1, len(sys.argv)):
#        print sys.argv [i],
        if sys.argv [i] == "-h":
            print
            print ("%s [-c <configFile>] [-l <logfile>] "
                            "[-cd [<configDir>]] [-d] [-h]" %
                            sys.argv[0])
            print
            print ("    -c <configFile> : configuration file to "
                                "process. Default is rtdConfig.ini")
            print ("    -l <logfile>    : logfile to send messages. "
                                "Default is rtdServer.log")
            print ("    -cd [<configDir>: directory to look for config"
                                " file. Default is '.'")
            print ("    -cd             : look for config file in "
                                "N:\Shared\ENG\EnvironmentServers")
            print ("    -d              : show debug info")
            print ("    -h              : print this help message and "
                                "exit")
            return
        elif sys.argv [i] == "-c" and i+1 < len(sys.argv):
            i += 1
#            print sys.argv [i],
            configFilename = sys.argv [i]
        elif sys.argv [i] == "-l" and i+1 < len(sys.argv):
            i += 1
#            print sys.argv [i],
            logFilename = sys.argv [i]
        elif sys.argv [i] == "-cd":
            if i+1 < len(sys.argv) and sys.argv [i+1] [0] != '-':
                configDirectory = sys.argv [i+1]
                i += 1
            else:
                configDirectory = "N:\Shared\ENG\EnvironmentServers"
        elif sys.argv[i] == "-d":
            debugMode = True
#    print
    print "opening logfile %s" % logFilename
    try:
        if debugMode:
            logging.basicConfig (level = logging.DEBUG,
                        filename=logFilename,
                        format = "%(asctime)s %(levelname)-7s"
                                " %(threadName)-13s: %(message)s")
        else:
            logging.basicConfig (level = logging.INFO,
                        filename=logFilename,
                        format = "%(asctime)s %(levelname)-7s"
                                " %(threadName)-13s: %(message)s")
    except IOError, err:
        print "unable to open log file %s: %s" % (logFilename,
                                                        err.strerror)
        return
    logging.info ("Starting rtdServer GUI")

    try:
        Config.readFile (configDirectory +os.sep +configFilename);

        mySched = asynSched.asynScheduler("MainThread")

        niBoxes = []
        niBoxInfo = Config.getNiBoxInfo()
        if niBoxInfo == None:
            raise Config.ConfigError ("no NI Box entries")

        for name in niBoxInfo.keys():
            niBoxes.append (niboxProto.niboxReader(mySched, name,
                            niBoxInfo[name][0], niBoxInfo[name][1]))

        rtdServer = rtdWex.rtdWexServer(mySched, Config.getPort(),
                                            Config.getRtdProbeInfo())
##
##        import SensorCache
##        for i in ["tr4.0", "tr4.1", "tr5.0", "tr5.2"]:
##            for j in range(0,11):
##                SensorCache.updateSensor(i+'.'+str(j), 25.0)
##
        probePoller = ProbePoller.ProbePoller (mySched)
        probePoller.handle_timer("None", None)

        try:
            mySched.loop()
        except KeyboardInterrupt:
            print "Terminated due to keyboard interrupt."

    except Config.ConfigError, err:
        print "Config error: %s" % err.args[0]
        logging.exception("Config error")

    finally:
        # the fat lady log message--i.e. the server thread isn't dead
        # unless we see this output.
        logging.info("stopping the rtdServer")
        logging.shutdown()

#=====================================================================#

if __name__ == "__main__":
    RunApp()
