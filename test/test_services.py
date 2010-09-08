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

import copy
#It's ugly I know....
from shinken_test import *


class TestConfig(ShinkenTest):
    #setUp is in shinken_test

    def get_svc(self):
        return self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")

    
    #Look if get_*_name return the good result
    def test_get_name(self):
        svc = self.get_svc()
        print svc.get_dbg_name()
        self.assert_(svc.get_name() == 'test_ok_0')
        self.assert_(svc.get_dbg_name() == 'test_host_0/test_ok_0')

    #getstate should be with all properties in dict class + id
    #check also the setstate
    def test___getstate__(self):
        svc = self.get_svc()
        cls = svc.__class__
        #We get teh state
        state = svc.__getstate__()
        #Check it's the good lenght
        self.assert_(len(state) == len(cls.properties) + len(cls.running_properties) + 1)
        #we copy the service
        svc_copy = copy.copy(svc)
        #reset the state in the original service
        svc.__setstate__(state)
        #And it should be the same :then before :)
        for p in cls.properties:
#            print getattr(svc_copy, p)
#            print getattr(svc, p)
            self.assert_(getattr(svc_copy, p) == getattr(svc, p))


    #Look if it can detect all incorrect cases
    def test_is_correct(self):
        svc = self.get_svc()

        #first it's ok
        self.assert_(svc.is_correct() == True)

        #Now try to delete a required property
        max_check_attempts = svc.max_check_attempts
        del svc.max_check_attempts
        self.assert_(svc.is_correct() == False)
        svc.max_check_attempts = max_check_attempts

        ###
        ### Now special cases
        ###

        #no contacts with notification enabled is a problem
        svc.notifications_enabled = True
        contacts = svc.contacts
        contact_groups = svc.contact_groups
        del svc.contacts
        del svc.contact_groups
        self.assert_(svc.is_correct() == False)
        #and with disabled it's ok
        svc.notifications_enabled = False
        self.assert_(svc.is_correct() == True)
        svc.contacts = contacts
        svc.contact_groups = contact_groups
        
        svc.notifications_enabled = True
        self.assert_(svc.is_correct() == True)

        #no check command
        check_command = svc.check_command
        del svc.check_command
        self.assert_(svc.is_correct() == False)
        svc.check_command = check_command
        self.assert_(svc.is_correct() == True)

        #no notification_interval
        notification_interval = svc.notification_interval
        del svc.notification_interval
        self.assert_(svc.is_correct() == False)
        svc.notification_interval = notification_interval
        self.assert_(svc.is_correct() == True)

        #No host
        host = svc.host
        del svc.host
        self.assert_(svc.is_correct() == False)
        svc.host = host
        self.assert_(svc.is_correct() == True)


    #Look for set/unset impacted states (unknown)
    def test_impact_state(self):
        svc = self.get_svc()
        ori_state = svc.state
        ori_state_id = svc.state_id
        svc.set_impact_state()
        self.assert_(svc.state == 'UNKNOWN')
        self.assert_(svc.state_id == 3)
        svc.unset_impact_state()
        self.assert_(svc.state == ori_state)
        self.assert_(svc.state_id == ori_state_id)

    def test_set_state_from_exit_status(self):
        svc = self.get_svc()
        #First OK
        svc.set_state_from_exit_status(0)
        self.assert_(svc.state == 'OK')
        self.assert_(svc.state_id == 0)
        self.assert_(svc.is_state('OK') == True)
        self.assert_(svc.is_state('o') == True)
        #Then warning
        svc.set_state_from_exit_status(1)
        self.assert_(svc.state == 'WARNING')
        self.assert_(svc.state_id == 1)
        self.assert_(svc.is_state('WARNING') == True)
        self.assert_(svc.is_state('w') == True)
        #Then Critical
        svc.set_state_from_exit_status(2)
        self.assert_(svc.state == 'CRITICAL')
        self.assert_(svc.state_id == 2)
        self.assert_(svc.is_state('CRITICAL') == True)
        self.assert_(svc.is_state('c') == True)
        #And unknown
        svc.set_state_from_exit_status(3)
        self.assert_(svc.state == 'UNKNOWN')
        self.assert_(svc.state_id == 3)
        self.assert_(svc.is_state('UNKNOWN') == True)
        self.assert_(svc.is_state('u') == True)

        #And something else :)
        svc.set_state_from_exit_status(99)
        self.assert_(svc.state == 'CRITICAL')
        self.assert_(svc.state_id == 2)
        self.assert_(svc.is_state('CRITICAL') == True)
        self.assert_(svc.is_state('c') == True)

        


if __name__ == '__main__':
    unittest.main()

    
