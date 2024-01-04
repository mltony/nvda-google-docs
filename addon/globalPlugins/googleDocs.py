#A part of the GoogleDocs addon for NVDA
#Copyright (C) 2024 Tony Malykh
#This file is covered by the GNU General Public License.
#See the file LICENSE  for more details.

import addonHandler
import api
import browseMode
import core
import globalPluginHandler
import tones
import ui

debug = False
if debug:
    f = open("C:\\Users\\tmal\\drp\\1.txt", "w", encoding='utf-8')
def mylog(s):
    if debug:
        print(str(s), file=f)
        f.flush()


originalGetAlternativeScript = None
def myGetAlternativeScript(selfself,gesture,script):
    result = originalGetAlternativeScript(selfself,gesture,script)
    tones.beep(500, 50)
    return result
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super(GlobalPlugin, self).__init__(*args, **kwargs)
        self.injectHooks()

    def terminate(self):
        self.restoreHooks()

    def injectHooks(self):
        global originalGetAlternativeScript
        originalGetAlternativeScript = browseMode.BrowseModeDocumentTreeInterceptor.getAlternativeScript
        browseMode.BrowseModeDocumentTreeInterceptor.getAlternativeScript = myGetAlternativeScript

    def restoreHooks(self):
        browseMode.BrowseModeDocumentTreeInterceptor.getAlternativeScript = originalGetAlternativeScript
