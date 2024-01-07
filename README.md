# Google Docs support for NVDA

This add-on enhances compatibility with Google Docs. This add-on works in browse mode by making QuickNav commands and cursor navigation commands work properly. For example, if you use Google Docs without this add-on, then pressing `H` will take you to the next heading, but only among the ones visible on the screen. This add-on fixes this behavior and `H` command will now take you to all headings in the document.

## Setup

For this add-on to work properly, we need to enable screenreader mode and Braille mode. In order to do that:
* Open any Google Doc.
* Press `Control+Alt+Z` until you hear "Screenreader support enabled".
* Press `Control+Alt+H` until you hear  "Braille support enabled".
* Press `NVDA+Space` to enter browse mode if you are in forms mode.

## Requirements

Supported browsers:

* Google Chrome
* Mozilla Firefox

For now this add-on requires "en_us" keyboard locale to be installed on your computer. This is required because the add-on needs to resolve Google Docs keystrokes and it does so in "en_us" locale. It will crash if "en_us" locale is not found. Pull requests to fix this behavior are welcome.

## Supported commands

Global commands:

* `NVDA+Alt+G` - toggle Google Docs accessibility (allows to temporarily disable functionality of this add-on)

QuickNav commands (their `Shift+` counterparts are omitted for brevity):

* `H` - next heading
* `1..6` - next heading level 1 through 6
* `K` - next link
* `L` - next list
* `I` - next list item
* `G` - next graphic
* `T` - next table

Navigation commands:

* `Arrows`
* `Control+Arrows`
* `Home`, `End`
* `Control+Home`, `Control+End`
` PageUp`, `PageDown`

## Known issues

* This add-on requires `en_us` to be installed on the computer.
* This add-on converts NVDA commands into Google Docs gestures. Therefore their behavior cannot be adjusted.
    * For example, pressing `H` repeatedly would wrap to the beginning of the document. This is inconvenient for NVDA users, but this is the default in Google Docs and unfortunately cannot be changed.
* Selection commands, such as `Shift+Arrows` are not supported at this time. Please switch to forms mode for selection.
