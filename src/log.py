#!/usr/bin/env python
#Copyright (C) 2009-2010 : 
#    Gabes Jean, naparuba@gmail.com 
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#
#This file is part of Shinken.
#
#Shinken is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#Shinken is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU Affero General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with Shinken.  If not, see <http://www.gnu.org/licenses/>.

import time

from borg import Borg
from brok import Brok

class Log(Borg):

    #We load the object where we will put log broks
    #with the 'add' method
    def load_obj(self, obj, name = None):
        self.obj = obj
        self.name = name

    #We enter a log message, we format it, and we add the log brok
    def log(self, message, format = None):
        print message
        if format == None:
            if self.name == None:
            #We format the log in UTF-8
                s = u'[%d] %s\n' % (int(time.time()), message.decode('UTF-8', 'replace'))
            else:
                s = u'[%d] [%s] %s\n' % (int(time.time()), self.name, message.decode('UTF-8', 'replace'))
        else:
            s = format % message

        #Wecreate and add the brok
        b = Brok('log', {'log' : s})
        self.obj.add(b)
