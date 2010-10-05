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
    #setUp is in shinken_test
    
    #Change ME :)
    def test_satellite_failed_check(self):
        print "Create a Scheduler dummy"
        creation_tab = {'scheduler_name' : 'scheduler-1', 'address' : '0.0.0.0', 'spare' : '0', 'port' : '9999'}
        s = SchedulerLink(creation_tab)
        s.timeout = 3
        s.data_timeout = 120
        s.port = 9999
        s.max_check_attempts = 4
        #Lie : we start at true here
        s.alive = True
        print s
        #Should be attempt = 0
        self.assert_(s.attempt == 0)
        #Now make bad ping, sould be unreach and dead (but not dead
        s.ping()
        self.assert_(s.attempt == 1)
        self.assert_(s.alive == True)
        self.assert_(s.reachable == False)

        #Now make bad ping, sould be unreach and dead (but not dead
        s.ping()
        self.assert_(s.attempt == 2)
        self.assert_(s.alive == True)
        self.assert_(s.reachable == False)

        #Now make bad ping, sould be unreach and dead (but not dead
        s.ping()
        self.assert_(s.attempt == 3)
        self.assert_(s.alive == True)
        self.assert_(s.reachable == False)

        #Ok, this time we go DEAD!
        s.ping()
        self.assert_(s.attempt == 4)
        self.assert_(s.alive == False)
        self.assert_(s.reachable == False)

        #Now set a OK ping (false because we won't open the port here...)
        s.set_alive()
        self.assert_(s.attempt == 0)
        self.assert_(s.alive == True)
        self.assert_(s.reachable == True)



if __name__ == '__main__':
    unittest.main()

