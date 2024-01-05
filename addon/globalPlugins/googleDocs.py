#A part of the GoogleDocs addon for NVDA
#Copyright (C) 2024 Tony Malykh
#This file is covered by the GNU General Public License.
#See the file LICENSE  for more details.

import addonHandler
import api
import browseMode
import core
from controlTypes import Role
import documentBase
import globalPluginHandler
import keyboardHandler
from NVDAObjects.IAccessible import IAccessible
from scriptHandler import script
import speech
import textInfos
import threading
from threading import Lock, Condition
import time
import tones
import types
import ui
import weakref
import winUser
import wx


debug = False
if debug:
    f = open("C:\\Users\\tmal\\drp\\1.txt", "w", encoding='utf-8')
def mylog(s):
    if debug:
        print(str(s), file=f)
        f.flush()

def executeAsynchronously(gen):
    """
    This function executes a generator-function in such a manner, that allows updates from the operating system to be processed during execution.
    For an example of such generator function, please see GlobalPlugin.script_editJupyter.
    Specifically, every time the generator function yilds a positive number,, the rest of the generator function will be executed
    from within wx.CallLater() call.
    If generator function yields a value of 0, then the rest of the generator function
    will be executed from within wx.CallAfter() call.
    This allows clear and simple expression of the logic inside the generator function, while still allowing NVDA to process update events from the operating system.
    Essentially the generator function will be paused every time it calls yield, then the updates will be processed by NVDA and then the remainder of generator function will continue executing.
    """
    if not isinstance(gen, types.GeneratorType):
        raise Exception("Generator function required")
    try:
        value = gen.__next__()
    except StopIteration:
        return
    l = lambda gen=gen: executeAsynchronously(gen)
    core.callLater(value, l)


def getUrl(obj):
    mylog("getUrl start")
    if not isinstance(obj, IAccessible):
        mylog("Not IA2")
        return None
    url = None
    o = obj
    while o is not None:
        mylog(f"while loop o:{o.role}")
        try:
            tag = o.IA2Attributes["tag"]
            mylog(f"tag={tag}")
        except AttributeError:
            mylog("AttributeError")
            break
        except KeyError:
            mylog("KeyError - try to continue")
            o = o.simpleParent
            continue
        if False:
            try:
                tmpUrl = o.IAccessibleObject.accValue(o.IAccessibleChildID)
                mylog(f"url = {tmpUrl.splitlines()[0]}")
            except:
                pass
        #if tag == "#document":
        if tag in [
            "#document", # for Chrome
            "body", # For Firefox
        ]:
            mylog("Good tag!")
            thisUrl = o.IAccessibleObject.accValue(o.IAccessibleChildID)
            mylog(f"url={thisUrl}")
            if thisUrl is not None and thisUrl.startswith("http"):
                url = thisUrl
        mylog("go to simpleParent")
        o = o.simpleParent
    mylog(f"Done; url={url}")
    return url

urlCache = weakref.WeakKeyDictionary()
def getUrlCached(interceptor, obj):
    #mylog("getUrlCached({interceptor}, {obj})")
    try:
        result = urlCache[interceptor]
        #mylog(f"Cache hit! Cached result = {result}")
        if result is not None:
            return result
    except KeyError:
        #mylog("Cache miss")
        pass
    url = getUrl(obj)
    #mylog(f"Resolved url = {url}")
    if url is not None and url.startswith("http"):
        #mylog(f"Storing in cache url = {url}")
        urlCache[interceptor] = url
    #mylog(f"Returning url={url}")
    return url

class Future:
    def __init__(self):
        self.__condition = Condition(Lock())
        self.__val = None
        self.__exc = None
        self.__is_set = False

    def get(self):
        with self.__condition:
            while not self.__is_set:
                self.__condition.wait()
            if self.__exc is not None:
                raise self.__exc
            return self.__val

    def set(self, val):
        with self.__condition:
            if self.__is_set:
                raise RuntimeError("Future has already been set")
            self.__val = val
            self.__is_set = True
            self.__condition.notify_all()

    def setException(self, val):
        with self.__condition:
            if self.__is_set:
                raise RuntimeError("Future has already been set")
            self.__exc = val
            self.__is_set = True
            self.__condition.notify_all()
            
    def isSet(self):
        return self.__is_set

    def done(self):
        return self.__is_set


def isMainNVDAThread():
    return threading.get_ident() == core.mainThreadId
def getFocusedObjectFromMainThread():
    def retrieveObjectProperties():
        focus = api.getFocusObject()
        return (focus, focus.role, focus.name)
    if isMainNVDAThread():
        result = retrieveObjectProperties()
    else:
        my_future = Future()
        def retrieveAndSetFuture():
            my_future.set(retrieveObjectProperties())
        wx.CallAfter(retrieveAndSetFuture)
        result = my_future.get()
    return result
def isGoogleDocs():
    mylog("isGD")
    focus = api.getFocusObject()
    # For some reason this call returns an object with Role.UNKNOWN
    # But we can extract treeInterceptor from it and that object makes more sense.
    # Below we will also retrieve focused object from main thread to perform additional checks.
    obj = focus.treeInterceptor.currentNVDAObject
    api.o = obj
    mylog(f"isgd role={obj.role}; parent={obj.simpleParent.role} name='{obj.name}'")
    try:
        interceptor = focus.treeInterceptor
    except AttributeError:
        mylog("Interceptor not found")
        return False

    url = getUrlCached(interceptor, obj)
    mylog(f"url = {url}")
    if url is None:
        mylog("url is none")
        return False
    if not url.startswith("https://docs.google.com/document/d/"):
        mylog("Url doesn't match")
        return False
    if True:
        # For some reason I couldn't figure out if we query focused object in this thread
        # It returns Role.UNKNOWN.
        # So we need to compute role and name in the main thread.
        # Happy hacking!
        focus, role, name = getFocusedObjectFromMainThread()
        if role not in [Role.EDITABLETEXT]:
            mylog(f"focus role doesn't match: found {role}")
            return False
        if name != 'Document content':
            mylog("focus object name doesn't match")
            return False
    mylog("yay!")
    return True


def getVkLetter(keyName):
    en_us_input_Hkl = 1033 + (1033 << 16)
    requiredMods, vk = winUser.VkKeyScanEx(keyName, en_us_input_Hkl)
    return vk


def makeVkEvent(vk, up=False):
    input = winUser.Input(type=winUser.INPUT_KEYBOARD)
    input.ii.ki.wVk = vk
    if up:
        input.ii.ki.dwFlags = winUser.KEYEVENTF_KEYUP
    return input
def makeVkInput(vkCodes, releaseShift=False):
    result = []
    if not isinstance(vkCodes, list):
        vkCodes = [vkCodes]
    if isinstance(vkCodes[-1], list):
        vkSequence = vkCodes[-1]
        vkCodes = vkCodes[:-1]
    else:
        vkSequence = []
    if releaseShift:
        #result.append(makeVkEvent(winUser.VK_SHIFT, up=True))
        result.append(makeVkEvent(winUser.VK_LSHIFT, up=True))
        result.append(makeVkEvent(winUser.VK_RSHIFT, up=True))
    for vk in vkCodes:
        result.append(makeVkEvent(vk))
    for vk in vkSequence:
        result.append(makeVkEvent(vk))
        result.append(makeVkEvent(vk, up=True))
    for vk in reversed(vkCodes):
        result.append(makeVkEvent(vk, up=True))
    return result

CONTROL_ALT = [winUser.VK_LCONTROL, winUser.VK_LMENU]
CONTROL_ALT_SHIFT = [winUser.VK_LCONTROL, winUser.VK_LMENU, winUser.VK_LSHIFT]
CA = CONTROL_ALT
CAS = CONTROL_ALT_SHIFT

def makeGoogleDocsCommand(modifiers, keys, releaseShift=False):
    return makeVkInput(modifiers + [[getVkLetter(c) for c in keys]], releaseShift=releaseShift)

def sendGoogleDocsCommand(modifiers, keys, releaseShift=False):
    with keyboardHandler.ignoreInjection():
        winUser.SendInput(makeGoogleDocsCommand(modifiers, keys, releaseShift=releaseShift))

KEYSTROKE_MAP = {}

def addQuickNavOverride(keystroke, modifiers, keys):
    def script_googleDocQuickNavOverridePrevious(gesture):
        sendGoogleDocsCommand(modifiers, 'p' + keys, releaseShift=True)
    def script_googleDocQuickNavOverrideNext(gesture):
        sendGoogleDocsCommand(modifiers, 'n' + keys)
    KEYSTROKE_MAP[keystroke] = script_googleDocQuickNavOverrideNext
    KEYSTROKE_MAP[f"shift+{keystroke}"] = script_googleDocQuickNavOverridePrevious

DEFERRED_SPEAK_TIMEOUT_SECONDS = 1.0
def deferredSpeakUnit(obj, unit, keystrokeCounterValue):
    yield 1 # Google Docs is blazing fast
    tBegin = time.time()
    tEnd = tBegin + DEFERRED_SPEAK_TIMEOUT_SECONDS
    text = None
    while time.time() < tEnd and keystrokeCounter == keystrokeCounterValue:
        info = obj.makeTextInfo(textInfos.POSITION_CARET)
        info.expand(unit)
        newText = info.text
        if text is None or newText != text:
            if text is not None:
                speech.cancelSpeech()
            speech.speakTextInfo(info)
            if text is not None:
                return
            else:
                text = newText
        yield 50

def addPassThroughScript(keystroke, unit=None):
    def script_passThrough(gesture):
        gesture.send()
        if unit is not None:
            focus = api.getFocusObject()
            executeAsynchronously(deferredSpeakUnit(focus, unit, keystrokeCounter))
    KEYSTROKE_MAP[keystroke] = script_passThrough

qq = addQuickNavOverride
if True:
    qq('h', CA, 'h')
    for i in range(1, 7):
        qq(str(i), CA, str(i))
    qq('k', CA, 'l')
    qq('l', CA, 'l')
    qq('i', CA, 'i')
    qq('g', CA, 'g')

    qq('t', CAS, 't')

PT = addPassThroughScript
if True:
    PT("upArrow", textInfos.UNIT_LINE)
    PT("downArrow", textInfos.UNIT_LINE)
    PT("control+home", textInfos.UNIT_LINE)
    PT("control+end", textInfos.UNIT_LINE)
    PT("pageUp", textInfos.UNIT_LINE)
    PT("pageDown", textInfos.UNIT_LINE)
    PT("leftArrow", textInfos.UNIT_CHARACTER)
    PT("rightArrow", textInfos.UNIT_CHARACTER)
    PT("home", textInfos.UNIT_CHARACTER)
    PT("end", textInfos.UNIT_CHARACTER)
    PT("control+upArrow", textInfos.UNIT_PARAGRAPH)
    PT("control+downArrow", textInfos.UNIT_PARAGRAPH)
    PT("control+leftArrow", textInfos.UNIT_WORD)
    PT("control+rightArrow", textInfos.UNIT_WORD)

def findOverrideScript(gesture):
    keystroke = gesture.identifiers[-1].split(':')[1]
    if keystroke.lower().startswith('3'):
        api.k = keystroke
        api.m = KEYSTROKE_MAP
    try:
        return KEYSTROKE_MAP[keystroke]
    except KeyError:
        return None

originalGetAlternativeScript = None
originalTableMovementScriptHelper = None
addonEnabled = True
keystrokeCounter = 0
def myGetAlternativeScript(selfself,gesture,script):
    global keystrokeCounter
    keystrokeCounter += 1
    result = originalGetAlternativeScript(selfself,gesture,script)
    if not selfself.passThrough:
        if addonEnabled and isGoogleDocs():
            overrideScript = findOverrideScript(gesture)
            if overrideScript is not None:
                return overrideScript
        else:
            pass
    return result

def myTableMovementScriptHelper(selfself, movement, axis):
    if isinstance(selfself, browseMode.BrowseModeDocumentTreeInterceptor):
        if addonEnabled and isGoogleDocs():
            # Here instead of executing table navigation gesture on treeInterceptor, we execute the same gesture on focused object instead.
            selfself = api.getFocusObject()
    originalTableMovementScriptHelper(selfself, movement, axis)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super(GlobalPlugin, self).__init__(*args, **kwargs)
        self.injectHooks()

    def terminate(self):
        self.restoreHooks()

    def injectHooks(self):
        global originalGetAlternativeScript, originalTableMovementScriptHelper
        originalGetAlternativeScript = browseMode.BrowseModeDocumentTreeInterceptor.getAlternativeScript
        browseMode.BrowseModeDocumentTreeInterceptor.getAlternativeScript = myGetAlternativeScript
        originalTableMovementScriptHelper = documentBase.DocumentWithTableNavigation._tableMovementScriptHelper
        documentBase.DocumentWithTableNavigation._tableMovementScriptHelper = myTableMovementScriptHelper

    def restoreHooks(self):
        browseMode.BrowseModeDocumentTreeInterceptor.getAlternativeScript = originalGetAlternativeScript
        documentBase.DocumentWithTableNavigation._tableMovementScriptHelper = originalTableMovementScriptHelper

    @script(description="Toggle Google Docs accessibility mode.", gestures=['kb:NVDA+alt+g'])
    def script_toggleGoogleDocAccessibility (self, gesture):
        global addonEnabled
        addonEnabled = not addonEnabled
        if addonEnabled:
            msg = _("Enabled Google Docs accessibility layer")
        else:
            msg = _("Disabled Google Docs accessibility layer")
        ui.message(msg)


    #@script(description="Speaks URL", gestures=['kb:NVDA+Home'])
    def script_speakUrl(self, gesture):
        #mylog("asdfasdf")
        obj = api.getFocusObject()
        url = getUrlCached(obj.treeInterceptor, obj)
        ui.message(str(url))
