#!/usr/bin/env python2.6
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


#
# This file is used to test reading and processing of config files
#

import os
import copy

from shinken_test import *
from shinken.log import logger
from shinken.objects.module import Module
from shinken.modules import pickle_retention_file_generic
from shinken.modules.pickle_retention_file_generic import get_instance 


modconf = Module()
modconf.module_name = "PickleRetentionGeneric"
modconf.module_type = pickle_retention_file_generic.properties['type']
modconf.properties = pickle_retention_file_generic.properties.copy()


class TestPickleRetentionBroker(ShinkenTest):
    #setUp is in shinken_test

    #Change ME :)
    def test_pickle_retention(self):
        print self.conf.modules
        #get our modules
        mod = pickle_retention_file_generic.Pickle_retention_generic(modconf, 'tmp/retention-test.dat')
        try :
            os.unlink(mod.path)
        except :
            pass

        sl = get_instance(mod)
        print "Instance", sl
        #Hack here :(
        sl.properties = {}
        sl.properties['to_queue'] = None
        sl.init()
        l = logger

        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")
        self.scheduler_loop(1, [[svc, 2, 'BAD | value1=0 value2=0']])

        self.sched.get_new_broks()
        
        # Saving the broks we got
        old_broks = copy.copy(self.sched.broks)

        # Now get a real broker object
        arbiter = Arbiter([''], False, False, False, None, None)

        arbiter.broks = self.sched.broks
        #updte the hosts and service in the scheduler in the retentino-file
        sl.hook_save_retention(arbiter)#, l)

        # Now we clean the source, like if we restart
        arbiter.broks.clear()
        
        self.assert_(len(arbiter.broks)==0)

        r = sl.hook_load_retention(arbiter)
        print len(old_broks), len(arbiter.broks)

        #We check we load them :)
        for b in old_broks.values():
            print "Look for good", b
            finded = False
            for b2 in arbiter.broks.values():
                if b2.id == b.id:
                    finded = True
            self.assert_(finded)

        #Ok, we can delete the retention file
        os.unlink(mod.path)




if __name__ == '__main__':
    unittest.main()

