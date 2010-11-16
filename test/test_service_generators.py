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

#It's ugly I know....
from shinken_test import *


class TestConfig(ShinkenTest):
    #Uncomment this is you want to use a specific configuration
    #for your test
    def setUp(self):
        self.setup_with_file('etc/nagios_service_generators.cfg')

    
    #Change ME :)
    def test_service_generators(self):
        
        host = self.sched.hosts.find_by_name("test_host_0")
        host.checks_in_progress = []
        host.act_depend_of = [] # ignore the router
        router = self.sched.hosts.find_by_name("test_router_0")
        router.checks_in_progress = []
        router.act_depend_of = [] # ignore the router
        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")

        print "All service of", "test_host_0"
        for s in host.services:
            print s.get_name()
        #We ask for 4 services with our disks :)
        svc_c = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "Generated Service C")
        svc_d = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "Generated Service D")
        svc_e = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "Generated Service E")
        svc_f = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "Generated Service F")
        svc_g = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "Generated Service G")
        
        self.assert_(svc_c != None)
        self.assert_(svc_d != None)
        self.assert_(svc_e != None)
        self.assert_(svc_f != None)
        self.assert_(svc_g != None)
        
        #two classics
        self.assert_(svc_c.check_command.args == ['C', '80%', '90%'])
        self.assert_(svc_d.check_command.args == ['D', '95%', '70%'])
        #a default parameters
        self.assert_(svc_e.check_command.args == ['E', '38%', '24%'])
        #and another one
        self.assert_(svc_f.check_command.args == ['F', '95%', '70%'])
        #and the tricky last one (with no value :) )
        self.assert_(svc_g.check_command.args == ['G', '38%', '24%'])


    #Change ME :)
    def test_service_generators_key_generator(self):
        
        host = self.sched.hosts.find_by_name("sw_0")
        host.checks_in_progress = []
        host.act_depend_of = [] # ignore the router

        print "All service of", "sw_0"
        for s in host.services:
            print s.get_name()

        #We ask for our 6*46 + 6 services with our ports :)
        #_ports			 Unit [1-6] Port [0-46]$(80%!90%)$,Unit [1-6] Port 47$(80%!90%)$
        for unit_id in xrange(1, 7):
            for port_id in xrange(0, 47):
                n = "Unit %d Port %d" % (unit_id, port_id)
                print "Look for port", 'Generated Service ' + n
                svc = self.sched.services.find_srv_by_name_and_hostname("sw_0", 'Generated Service ' + n)
                self.assert_(svc != None)
        for unit_id in xrange(1, 7):
            port_id = 47
            n = "Unit %d Port %d" % (unit_id, port_id)
            print "Look for port", 'Generated Service ' + n
            svc = self.sched.services.find_srv_by_name_and_hostname("sw_0", 'Generated Service ' + n)
            self.assert_(svc != None)



    def test_service_generators_array(self):

        host = self.sched.hosts.find_by_name("sw_1")
        host.checks_in_progress = []
        host.act_depend_of = [] # ignore the router

        print "All service of", "sw_1"
        for s in host.services:
            print s.get_name()

        svc = self.sched.services.find_srv_by_name_and_hostname("sw_1", 'Generated Service Gigabit0/1')
        self.assert_(svc != None)
        self.assert_(svc.check_command.call == 'check_service!1!80%!90%')

        svc = self.sched.services.find_srv_by_name_and_hostname("sw_1", 'Generated Service Gigabit0/2')
        self.assert_(svc != None)
        self.assert_(svc.check_command.call == 'check_service!2!80%!90%')

        svc = self.sched.services.find_srv_by_name_and_hostname("sw_1", 'Generated Service Ethernet0/1')
        self.assert_(svc != None)
        self.assert_(svc.check_command.call == 'check_service!3!80%!95%')

        svc = self.sched.services.find_srv_by_name_and_hostname("sw_1", 'Generated Service ISDN1')
        self.assert_(svc != None)
        self.assert_(svc.check_command.call == 'check_service!4!80%!95%')


if __name__ == '__main__':
    unittest.main()

