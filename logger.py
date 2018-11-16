
# todo : use a proper logger 
from datetime import datetime as dt

class Logger():

  def __init__(self, level):
    self.setLevel(level)

  def setLevel(self, lvl):
  	l = int(lvl)
  	if l * 0 == 0: # ensure its a number
  	  self.level = l
  	else:
  	  __log__("What is this value '%s' passed to logger.setLevel?"%str(l), "Hmmm")

  def setDebug(self):
    self.setLevel(0)

  def setInfo(self):
    self.setLevel(0)

  def setWarn(self):
    self.setLevel(0)

  def setError(self):
    self.setLevel(0)

  # log and terminate the program, default code   
  def fatal(self, msg, exitCode=1):
    __log__(msg, "FATAL")
    exit(exitCode)

  def err(self, msg):
    if self.level < 4:
      __log__(msg, "ERROR")

  def warn(self, msg):
    if self.level < 3:
      __log__(msg, "WARN")

  def info(self, msg):
    if self.level < 2:
      __log__(msg, "INFO")

  def db(self, msg):
    if self.level < 1:
      __log__(msg, "DEBUG")



def __log__(msg, lvl="DEBUG"):
  print("%s %s::%s" %(dt.now().strftime("%y %b %d %H:%M:%S.%f"), lvl, msg))

log = Logger(1)

