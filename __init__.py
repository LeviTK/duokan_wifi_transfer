#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__ = 'GPL v3'
__copyright__ = '2024, Your Name'
__docformat__ = 'restructuredtext en'

from calibre.customize import InterfaceActionBase

class DuokanWifiBase(InterfaceActionBase):
    '''
    This class is a simple wrapper that provides information about the actual
    plugin class. The actual interface plugin class is called InterfacePlugin
    and is defined in the ui.py file, as specified in the actual_plugin field
    below.
    '''
    name                = '多看阅读WiFi传书'
    description         = '通过WiFi将书籍传输到多看阅读'
    supported_platforms = ['windows', 'osx', 'linux']
    author             = 'Your Name'
    version            = (1, 2, 0)
    minimum_calibre_version = (2, 0, 0)

    #: This field defines the GUI plugin class that contains all the code
    #: that actually does something. Its specified as a string to avoid
    #: loading the class until the plugin is actually used.
    actual_plugin       = 'calibre_plugins.duokan_wifi_transfer.ui:InterfacePlugin'
