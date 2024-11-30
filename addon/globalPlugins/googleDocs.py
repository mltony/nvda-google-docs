#A part of the GoogleDocs addon for NVDA
#Copyright (C) 2024 Tony Malykh
#This file is covered by the GNU General Public License.
#See the file LICENSE  for more details.

import addonHandler
import api
import browseMode
import core
from controlTypes import Role, OutputReason
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
from logHandler import log
import gui

debug = True
if debug:
    f = open("C:\\Users\\tony\\1.txt", "w", encoding='utf-8')
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

initSuccess = False
isInGoogleDocsMainEditor = False
def onPostFocusOrURLChange():
    global isInGoogleDocsMainEditor
    url = api.getCurrentURL()
    if not isGoogleDocsUrl(url):
        isInGoogleDocsMainEditor = False
        return
    focus = api.getFocusObject()
    isInGoogleDocsMainEditor = (
        focus.role == Role.EDITABLETEXT
        and focus.simplePrevious is None
        and focus.simpleNext is None
        and focus.parent is not None
        and focus.parent.role == Role.DOCUMENT
    )
    if isInGoogleDocsMainEditor:
        #tones.beep(1000, 50)
        pass

def onPostNvdaStartup():
    try:
        post = api.postFocusOrURLChange
    except AttributeError:
        wx.CallAfter(
            gui.messageBox,
            _(
                "Error initializing Google Docs accessibility add-on.\n"
                "Google Docs accessibility requires BrowserNav v2.6.2 or later add-on to be installed.\n"
                "However it is either not installed, or failed to initialize.\n"
                "Please install the latest BrowserNav add-on from add-on store and restart NVDA.\n",
            ),
            _("Google Docs accessibility add-on Error"),
            wx.ICON_ERROR | wx.OK,
        )
        return
    post.register(onPostFocusOrURLChange)
    global initSuccess
    initSuccess = True

    

core.postNvdaStartup.register(onPostNvdaStartup)


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

def isGoogleDocsUrl(url):
    if url is None:
        return None
    return url.startswith("https://docs.google.com/document/")

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
            speech.speakTextInfo(info, unit=unit, reason=OutputReason.CARET)
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
    # Google docs screenreader commands for reference:
    # https://support.google.com/docs/answer/179738?sjid=11768555839712713642-NC#zippy=%2Cpc-shortcuts
    qq('h', CA, 'h')
    for i in range(1, 7):
        qq(str(i), CA, str(i))
    qq('k', CA, 'l')  # Jump to next hyperlink: CA+N CA+L
    qq('l', CA, 'o')
    qq('i', CA, 'i')
    qq('g', CA, 'g')
    qq('c', CA, 'c')  # Next comment CA+N CA+C

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
        if addonEnabled and isInGoogleDocsMainEditor:
            overrideScript = findOverrideScript(gesture)
            if overrideScript is not None:
                return overrideScript
        else:
            pass
    return result

def myTableMovementScriptHelper(selfself, movement, axis):
    if isinstance(selfself, browseMode.BrowseModeDocumentTreeInterceptor):
        if addonEnabled and isInGoogleDocsMainEditor:
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
        if not initSuccess:
            msg = _("Google Docs Accessibility add-on failed to initialize.")
            ui.message(msg)
            return
        global addonEnabled
        addonEnabled = not addonEnabled
        if addonEnabled:
            msg = _("Enabled Google Docs accessibility layer")
        else:
            msg = _("Disabled Google Docs accessibility layer")
        ui.message(msg)
