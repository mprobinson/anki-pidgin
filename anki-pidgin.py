# Copyright: 2013 Mike Robinson
# -*- coding: utf-8 -*-
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

# Add-on for Anki 2
# Automatically set away status of Pidgin using dbus


from anki.hooks import wrap
from aqt import mw
import threading
import dbus
import gobject
import time
from dbus.mainloop.glib import DBusGMainLoop

plugin = {}
plugin['reviewingState'] = False
plugin['startTime'] = 0
plugin['reportedMinutes'] = 0
plugin['savedStatus'] = None

autoreplySent = set()

def stateWatcher(newstate, *args):
    global plugin
    if ((mw.state == "overview") and (newstate == "review")):
        print "entering review"
        plugin['reviewingState'] = True
        plugin['startTime'] = time.time()
        plugin['reportedMinutes'] = 0
        autoreplySent.clear()
        pidginLock.acquire()
        plugin['savedStatus'] = purple.PurpleSavedstatusGetCurrent()
        pidginLock.release()
        # force refresh in case somebody messages before the timer
        refreshPidginAway()
    if ((plugin['reviewingState'] == True) and (newstate == "deckBrowser" or newstate == "overview")):
        print "leaving review"
        plugin['reviewingState'] = False
        if plugin['savedStatus'] is not None:
            pidginLock.acquire()
            purple.PurpleSavedstatusActivate(plugin['savedStatus'])
            pidginLock.release()
            plugin['savedStatus'] = None

def imReceived(account, sender, message, conversation, flags):
    print sender, "said:", message, threading.currentThread()
    if not plugin['reviewingState']:
        return
    # send maximum of one reply per sessions to avoid message loops
    if conversation not in autoreplySent:
        pidginLock.acquire()
        purple.PurpleConvImSend(purple.PurpleConvIm(conversation),
                                "[autoreply] I am currently studying using Anki, back in " + str(plugin['reportedMinutes']) + " minutes. See my away status for progress report.")
        pidginLock.release()
        autoreplySent.add(conversation)

def refreshPidginAway():
    global plugin
    if not plugin['reviewingState']:
        return True # repeating timer
    endtime = mw.col.conf['timeLim'] + plugin['startTime']
    mins = int(round((endtime - time.time())/60))
    # check if time changed enough to report
    if (mins != plugin['reportedMinutes']):
        pidginLock.acquire()
        # PURPLE_STATUS_UNAVAILABLE
        status = purple.PurpleSavedstatusNew("", 3)
        purple.PurpleSavedstatusSetMessage(status, "Back in " + str(mins) + " minutes.")
        purple.PurpleSavedstatusActivate(status)
        print "Setting away message", mins
        pidginLock.release()
        plugin['reportedMinutes'] = mins
    return True # repeating timer

# don't send multiple dbus messages at once
pidginLock = threading.Lock()

mw.moveToState = wrap(mw.moveToState, stateWatcher, "before")

mainLoop = gobject.MainLoop()

# required for running MainLoop is a separate thread
gobject.threads_init()

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
obj = bus.get_object("im.pidgin.purple.PurpleService",
                      "/im/pidgin/purple/PurpleObject")
purple = dbus.Interface(obj, "im.pidgin.purple.PurpleInterface")
bus.add_signal_receiver(imReceived,
                        dbus_interface="im.pidgin.purple.PurpleInterface",
                        signal_name="ReceivedImMsg")
                        
def asyncDbus():
    # check away message every 10 seconds
    gobject.timeout_add(10*1000, refreshPidginAway)
    mainLoop.run()

dbusThread = threading.Thread(target=asyncDbus)
dbusThread.daemon = True
dbusThread.start()
