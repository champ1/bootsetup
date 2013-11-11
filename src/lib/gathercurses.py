#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: set et ai sta sw=2 ts=2 tw=0:
"""
Curses (urwid) BootSetup configuration gathering.
"""
__copyright__ = 'Copyright 2013-2014, Salix OS'
__license__ = 'GPL2+'

import gettext
import gobject
import urwid
import re
import math
import subprocess
from config import *
import salix_livetools_library as sltl
import urwid_wicd.curses_misc as urwicd
from lilo import *
from grub2 import *

class GatherCurses:
  """
  UI in curses/urwid to gather information about the configuration to setup.
  """
  
  # Other potential color schemes can be found at:
  # http://excess.org/urwid/wiki/RecommendedPalette
  _palette = [
      ('body', 'light gray', 'black'),
      ('header', 'dark red', 'light gray', 'bold'),
      ('footer', 'light green', 'black', 'bold'),
      ('footer_key', 'yellow', 'black', 'bold'),
      ('strong', 'white', 'black', 'bold'),
      ('focusable', 'light green', 'black'),
      ('non_focusable', 'brown', 'black'),
      ('focus', 'black', 'light green'),
      ('focus_edit', 'yellow', 'black'),
      ('combobody', 'black', 'light gray'),
      ('combofocus', 'black', 'light green'),
    ]
  _view = None
  _loop = None
  _comboBoxes = [] # hack for ComboBox
  _comboBoxArrow = "   ↓"
  _labelPerDevice = {}

  def __init__(self, bootsetup, version, bootloader = None, target_partition = None, is_test = False, use_test_data = False):
    self._bootsetup = bootsetup
    self._version = version
    self.cfg = Config(bootloader, target_partition, is_test, use_test_data)
    print u"""
bootloader         = {bootloader}
target partition   = {partition}
MBR device         = {mbr}
disks:{disks}
partitions:{partitions}
boot partitions:{boot_partitions}
""".format(bootloader = self.cfg.cur_bootloader, partition = self.cfg.cur_boot_partition, mbr = self.cfg.cur_mbr_device, disks = "\n - " + "\n - ".join(map(" ".join, self.cfg.disks)), partitions = "\n - " + "\n - ".join(map(" ".join, self.cfg.partitions)), boot_partitions = "\n - " + "\n - ".join(map(" ".join, self.cfg.boot_partitions)))
    self.lilo = self.grub2 = None
    self.ui = urwid.raw_display.Screen()
    self.ui.set_mouse_tracking()
    self._palette.extend(bootsetup._palette)
  
  def run(self):
    self._createView()
    self._changeBootloaderSection()
    self._loop = urwid.MainLoop(self._view, self._palette, handle_mouse = True, unhandled_input = self._handleKeys)
    # hack for ComboBox
    for c in self._comboBoxes:
      c.build_combobox(self._view, self._loop.screen, c.displayRows)
    if self.cfg.cur_bootloader == 'lilo':
      self._radioLiLo.set_state(True)
    elif self.cfg.cur_bootloader == 'grub2':
      self._radioGrub2.set_state(True)
    self._loop.run()
  
  def _infoDialog(self, message):
    self._bootsetup.info_dialog(message, parent = self._view)

  def _errorDialog(self, message):
    self._bootsetup.error_dialog(message, parent = self._view)

  def _hackComboBox(self, comboBox):
    comboBox.DOWN_ARROW = self._comboBoxArrow
    comboBox.displayRows = 5
    if self._loop and self._loop.screen.started:
      comboBox.build_combobox(self._view, self._loop.screen, comboBox.displayRows)
    else:
      self._comboBoxes.append(comboBox)
    return comboBox

  def _createEdit(self, caption = u'', edit_text = u'', multiline = False, align = 'left', wrap = 'space', allow_tab = False, edit_pos = None, layout = None, mask = None):
    edit = urwid.Edit(caption, edit_text, multiline, align, wrap, allow_tab, edit_pos, layout, mask)
    return urwid.AttrMap(edit, 'focusable', 'focus_edit')

  def _createButton(self, label, on_press = None, user_data = None):
    btn = urwid.Button(label, on_press, user_data)
    return urwid.AttrMap(btn, 'focusable', 'focus')

  def _createRadioButton(self, group, label, state = "first True", on_state_change = None, user_data = None):
    if isinstance(label, basestring):
      label = ('focusable', label)
    radio = urwid.RadioButton(group, label, state, on_state_change, user_data)
    return radio

  def _createCenterButtonsWidget(self, buttons, h_sep = 2, v_sep = 0):
    maxLen = 0
    for button in buttons:
      if not hasattr(button, 'get_label') and hasattr(button, 'original_widget'):
        button = button.original_widget
      maxLen = max(maxLen, len(button.get_label()))
    return urwid.GridFlow(buttons, cell_width = maxLen + len('<  >'), h_sep = h_sep, v_sep = v_sep, align = "center")

  def _createView(self):
    """
+=======================================+
|                 Title                 |
+=======================================+
| Introduction text                     |
+---------------------------------------+
| Bootloader: (×) LiLo (_) Grub2        |
| MBR Device:  |_____________ ↓|        | <== ComboBox thanks to wicd
| Grub2 files: |_____________ ↓|        | <== Grub2 only
| +-----------------------------------+ | --+
| |Dev.|FS  |Type |Label      |Actions| |   |
| |sda1|ext4|Salix|Salix14____|<↑><↓> | |   |
| |sda5|xfs |Arch |ArchLinux__|<↑><↓> | |   +- <== LiLo only
| +-----------------------------------+ |   |
| <Edit config>    <Undo custom config> | --+
|            <Install>                  |
+=======================================+
| H: Help, A: About, Q: Quit            | <== Action keyboard thanks to wicd
+=======================================+
    """
    # header
    txtTitle = urwid.Text(_("BootSetup curses, version {ver}").format(ver = self._version), align = "center")
    header = urwid.AttrMap(urwid.Pile([txtTitle, urwid.Divider()]), 'header')
    # footer
    keys = [
        ('H', " " + _("Help")),
        ('A', " " + _("About")),
        ('Q / F10', " " + _("Quit")),
      ]
    keysColumns = urwicd.OptCols(keys, self._handleKeys, attrs = ('footer_key', 'footer'))
    footer = urwid.AttrMap(keysColumns, 'footer')
    # intro
    introHtml = _("<b>BootSetup will install a new bootloader on your computer.</b> \n\
\n\
A bootloader is required to load the main operating system of a computer and will initially display \
a boot menu if several operating systems are available on the same computer.")
    intro = map(lambda line: ('strong', line.replace("<b>", "").replace("</b>", "") + "\n") if line.startswith("<b>") else line, introHtml.split("\n"))
    intro[-1] = intro[-1].strip() # remove last "\n"
    txtIntro = urwid.Text(intro)
    # bootloader type section
    lblBootloader = urwid.Text(_("Bootloader:"))
    radioGroupBootloader = []
    self._radioLiLo = self._createRadioButton(radioGroupBootloader, "LiLo", state = False, on_state_change = self._onLiLoChange)
    self._radioGrub2 = self._createRadioButton(radioGroupBootloader, "Grub2", state = False, on_state_change = self._onGrub2Change)
    bootloaderTypeSection = urwid.Columns([lblBootloader, self._radioLiLo, self._radioGrub2], focus_column = 1)
    # mbr device section
    mbrDeviceSection = self._createMbrDeviceSectionView()
    # bootloader section
    self._bootloaderSection = urwid.WidgetPlaceholder(urwid.Text(""))
    # install section
    btnInstall = self._createButton(_("_Install bootloader").replace("_", ""), on_press = self._onInstall)
    installSection = self._createCenterButtonsWidget([btnInstall])
    # body
    bodyList = [urwid.Divider(), txtIntro, urwid.Divider('─', bottom = 1), bootloaderTypeSection, mbrDeviceSection, urwid.Divider(), self._bootloaderSection, urwid.Divider('─', top = 1, bottom = 1), installSection]
    body = urwid.AttrWrap(urwid.ListBox(urwid.SimpleListWalker(bodyList)), 'body')
    frame = urwid.Frame(body, header, footer, focus_part = 'body')
    self._view = frame

  def _createMbrDeviceSectionView(self):
    comboList = []
    for d in self.cfg.disks:
      comboList.append(" - ".join(d))
    comboBox = self._hackComboBox(urwicd.ComboBox(_("Install bootloader on:"), comboList, focus = 0, attrs = ('focusable', 'non-focusable'), focus_attr = 'focus'))
    return comboBox

  def _createBootloaderSectionView(self):
    if self.cfg.cur_bootloader == 'lilo':
      listDev = [urwid.Text(_("Partition"))]
      listFS = [urwid.Text(_("File system"))]
      listType = [urwid.Text(_("Operating system"))]
      listLabel = [urwid.Text(_("Boot menu label"))]
      listAction = [urwid.Text("")]
      self._labelPerDevice = {}
      for p in self.cfg.boot_partitions:
        dev = p[0]
        fs = p[1]
        ostype = p[3]
        label = re.sub(r'[()]', '', re.sub(r'_\(loader\)', '', re.sub(' ', '_', p[4]))) # lilo does not like spaces and pretty print the label
        listDev.append(urwid.Text(dev))
        listFS.append(urwid.Text(fs))
        listType.append(urwid.Text(ostype))
        self._labelPerDevice[dev] = label
        editLabel = self._createEdit(edit_text = label, wrap = 'clip')
        urwid.connect_signal(editLabel.original_widget, 'change', self._onLabelChange, dev)
        listLabel.append(editLabel)
        listAction.append(urwid.GridFlow([self._createButton("↑", on_press = self._moveLineUp, user_data = p[0]), self._createButton("↓", on_press = self._moveLineDown, user_data = p[0])], cell_width = 5, h_sep = 1, v_sep = 1, align = "center"))
      colDev = urwid.Pile(listDev)
      colFS = urwid.Pile(listFS)
      colType = urwid.Pile(listType)
      colLabel = urwid.Pile(listLabel)
      colAction = urwid.Pile(listAction)
      self._liloTable = urwid.Columns([colDev, colFS, colType, colLabel, colAction])
      table = urwid.LineBox(self._liloTable)
      btnEdit = self._createButton(_("_Edit configuration").replace("_", ""), on_press = self._editLiLoConf)
      btnCancel = self._createButton(_("_Undo configuration").replace("_", ""), on_press = self._cancelLiLoConf)
      pile = urwid.Pile([table, self._createCenterButtonsWidget([btnEdit, btnCancel])])
      return pile
    elif self.cfg.cur_bootloader == 'grub2':
      comboList = []
      for p in self.cfg.partitions:
        comboList.append(" - ".join(p))
      comboBox = self._hackComboBox(urwicd.ComboBox(_("Install Grub2 files on:"), comboList, focus = 0, attrs = ('focusable', 'non-focusable'), focus_attr = 'focus'))
      return comboBox
    else:
      return urwid.Text("")

  def _changeBootloaderSection(self):
    self._bootloaderSection.original_widget = self._createBootloaderSectionView()

  def _handleKeys(self, key):
    if key in ('q', 'Q', 'f10'):
      self.main_quit()

  def _onLiLoChange(self, radioLiLo, newState):
    if newState:
      self.cfg.cur_bootloader = 'lilo'
      self._changeBootloaderSection()

  def _onGrub2Change(self, radioGrub2, newState):
    if newState:
      self.cfg.cur_bootloader = 'grub2'
      self._changeBootloaderSection()

  def _onLabelChange(self, editLabel, newText, device):
    self._labelPerDevice[device] = newText

  def _findDevPosition(self, device):
    colDevice = self._liloTable.widget_list[0]
    for i, line in enumerate(colDevice.widget_list):
      if i == 0: # skip header
        continue
      if line.get_text()[0] == device:
        return i
    return None

  def _moveLineUp(self, button, device):
    pos = self._findDevPosition(device)
    if pos > 1: # 0 = header
      for col, types in self._liloTable.contents:
        old = col.widget_list[pos]
        del col.widget_list[pos]
        col.widget_list.insert(pos - 1, old)

  def _moveLineDown(self, button, device):
    pos = self._findDevPosition(device)
    if pos < len(self._liloTable.widget_list[0].item_types) - 1:
      for col, types in self._liloTable.contents:
        old = col.widget_list[pos]
        del col.widget_list[pos]
        col.widget_list.insert(pos + 1, old)

  def _editLiLoConf(self, button):
    self._infoDialog(u"TODO edit…")

  def _cancelLiLoConf(self, button):
    self._infoDialog(u"TODO cancel…")

  def _onInstall(self, btnInstall):
    self._infoDialog(u"TODO install\n" + unicode(self._labelPerDevice))
    self.main_quit()

  def main_quit(self):
    if self.lilo:
      del self.lilo
    if self.grub2:
      del self.grub2
    print "Bye _o/"
    raise urwid.ExitMainLoop()