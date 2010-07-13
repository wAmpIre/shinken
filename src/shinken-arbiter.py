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


#This is the class of the Arbiter. It's role is to read configuration,
#cuts it, and send it to other elements like schedulers, reactionner 
#or pollers. It is responsible for hight avaibility part. If a scheduler
#is dead,
#it send it's conf to another if available.
#It also read order form users (nagios.cmd) and send orders to schedulers.

import os
#import re
import time
import sys
import Pyro.core
import select
import getopt
import random


from util import to_bool
#from scheduler import Scheduler
from config import Config
from external_command import ExternalCommand
from dispatcher import Dispatcher
from daemon import Daemon
from log import Log


VERSION = "0.1"


#Interface for Brokers
#They connect here and get all broks (data for brokers)
#datas must be ORDERED! (initial status BEFORE update...)
class IBroks(Pyro.core.ObjBase):
    #we keep sched link
    def __init__(self, arbiter):
        Pyro.core.ObjBase.__init__(self)
        self.arbiter = arbiter
        self.running_id = random.random()


    #Broker need to void it's broks?
    def get_running_id(self):
        return self.running_id

		
    #poller or reactionner ask us actions
    #def get_broks(self):
    #    #print "We ask us broks"
    #    res = self.arbiter.get_broks()
    #	#print "Sending %d broks" % len(res)#, res
    #    self.arbiter.nb_broks_send += len(res)
    #    return res


    #Ping? Pong!
    def ping(self):
        return None


#Interface for the other Arbiter
#It connect, and we manage who is the Master, slave etc. 
#Here is a also a fnction to have a new conf from the master
class IArbiters(Pyro.core.ObjBase):
    #we keep arbiter link
    def __init__(self, arbiter):
        Pyro.core.ObjBase.__init__(self)
        self.arbiter = arbiter
        self.running_id = random.random()


    #Broker need to void it's broks?
    def get_running_id(self):
        return self.running_id


    def have_conf(self, magic_hash):
        #I've got a conf and the good one
        if self.arbiter.have_conf and self.arbiter.conf.magic_hash == magic_hash:
            return True
        else: #No conf or a bad one
            return False


    #The master Arbiter is sending us a new conf. Ok, we take it
    def put_conf(self, conf):
        self.arbiter.conf = conf
        print "Get conf:", self.arbiter.conf
        self.arbiter.have_conf = True
        print "Just after reception"
        self.arbiter.must_run = False


    #Ping? Pong!
    def ping(self):
        return None


    #the master arbiter ask me to do not run!
    def do_not_run(self):
        #If i'm the master, just FUCK YOU!
        if self.arbiter.is_master:
            print "Some fucking idiot ask me to do not run. I'm a proud master, so I'm still running"
        #Else I'm just a spare, so I listen to my master
        else:
            print "Someone ask me to do not run"
            self.arbiter.last_master_speack = time.time()
            self.arbiter.must_run = False


#Main Arbiter Class
class Arbiter(Daemon):


    properties = {
        'workdir' : {'default' : '/usr/local/shinken/src/var', 'pythonize' : None},
        'pidfile' : {'default' : '/usr/local/shinken/src/var/arbiterd.pid', 'pythonize' : None},
        #'port' : {'default' : '7768', 'pythonize' : to_int},
        #'host' : {'default' : '0.0.0.0', 'pythonize' : None},
        'user' : {'default' : 'shinken', 'pythonize' : None},
        'group' : {'default' : 'shinken', 'pythonize' : None},
        'idontcareaboutsecurity' : {'default' : '0', 'pythonize' : to_bool}
        }


    def __init__(self, config_files, is_daemon, do_replace, verify_only, debug, debug_file):
        self.config_file = config_files[0]
        self.config_files = config_files
        self.is_daemon = is_daemon
        self.verify_only = verify_only
        self.do_replace = do_replace
        self.debug = debug
        self.debug_file = debug_file

        #From daemon to manage signal. Call self.manage_signal if
        #exists, a dummy function otherwise
        self.set_exit_handler()
        self.broks = {}
        self.is_master = False
        self.me = None

        self.nb_broks_send = 0


    #Use for adding broks
    def add(self, b):
        self.broks[b.id] = b


    #Call by brokers to have broks
    #We give them, and clean them!
    #def get_broks(self):
    #    res = self.broks
    #    #They are gone, we keep none!
    #    self.broks = {}
    #    return res


    #We must push our broks to the broker
    #because it's stupid to make a crossing connexion
    #so we find the broker responbile for our broks,
    #and we send him it
    #TODO : better find the broker, here it can be dead?
    #or not the good one?
    def push_broks_to_broker(self):
        for brk in self.conf.brokers:
            if brk.manage_arbiters:
                is_send = brk.push_broks(self.broks)
                if is_send:
                    #They are gone, we keep none!
                    self.broks = {}



    #Load the external commander
    def load_external_command(self, e):
        self.external_command = e
        self.fifo = e.open()
        
        
    def main(self):
        #Log will be broks
        self.log = Log()
        self.log.load_obj(self)

        self.print_header()
        for line in self.get_header():
            self.log.log(line)#, format = 'TOTO %s\n')
	    
	#Use to know if we must still be alive or not
        self.must_run = True
        
        print "Loading configuration"
        self.conf = Config()
        #The config Class must have the USERN macro
        #There are 256 of them, so we create online
        Config.fill_usern_macros()
        
        #REF: doc/shinken-conf-dispatching.png (1)
        self.conf.read_config(self.config_files)
        
	#Maybe conf is already invalid
        if not self.conf.conf_is_correct:
            print "***> One or more problems was encountered while processing the config files..."
            sys.exit(1)


        #************** Change Nagios2 names to Nagios3 ones ******
        self.conf.old_properties_names_to_new()

        #************* Print warning about useless parameters in Shinken **************"
        self.conf.notice_about_useless_parameters()

	#print "****************** Create Template links **********"
        self.conf.linkify_templates()

        #print "****************** Inheritance *******************"
        self.conf.apply_inheritance()

        #print "****************** Explode ***********************"
        self.conf.explode()

        #print "***************** Create Name reversed list ******"
        self.conf.create_reversed_list()

        #print "***************** Cleaning Twins *****************"
        self.conf.remove_twins()

        #print "****************** Implicit inheritance *******************"
        self.conf.apply_implicit_inheritance()

        #print "****************** Fill default ******************"
        self.conf.fill_default()
        
        #print "****************** Clean templates ******************"
        self.conf.clean_useless()
        
        #print "****************** Pythonize ******************"
        self.conf.pythonize()
        
        #print "****************** Linkify ******************"
        self.conf.linkify()
        
        #print "*************** applying dependancies ************"
        self.conf.apply_dependancies()

        #Hacking some global parameter inherited from Nagios to create
        #on the fly some Broker modules like for status.dat parameters
        #or nagios.log one if there are no already available
        self.conf.hack_old_nagios_parameters()
        
        #print "************** Exlode global conf ****************"
        self.conf.explode_global_conf()
        
        #print "****************** Correct ?******************"
        self.conf.is_correct()

        #If the conf is not correct, we must get out now
        if not self.conf.conf_is_correct:
            print "Configuration is incorrect, sorry, I bail out"
            sys.exit(1)



        #self.conf.dump()

        #from guppy import hpy
        #hp=hpy()
        #print hp.heap()
        #print hp.heapu()


        #Search wich Arbiterlink I am
        for arb in self.conf.arbiterlinks:
            if arb.is_me():
                arb.need_conf = False
                self.me = arb
                print "I am the arbiter :", arb.get_name()
                print "Am I the master?", not self.me.spare
            else: #not me
                arb.need_conf = True


        if self.me == None:
            print "Error : I cannot find my own Arbiter object, I bail out"
            print "To solve it : please change the host_name parameter in the object Arbiter"
            print "in the file shinken-specific.cfg. Thanks."
            sys.exit(1)


	#If I am a spare, I must wait a (true) conf from Arbiter Master
        self.wait_conf = self.me.spare
        
        #print "Dump realms"
        #for r in self.conf.realms:
        #    print r.get_name(), r.__dict__
        print "\n"
        
        #REF: doc/shinken-conf-dispatching.png (2)
        Log().log("Cutting the hosts and services into parts")
        self.confs = self.conf.cut_into_parts()

        #If the conf can be incorrect here if the cut into parts see errors like
	#a realm with hosts and not scehdulers for it
        if not self.conf.conf_is_correct:
            print "Configuration is incorrect, sorry, I bail out"
            sys.exit(1)

        Log().log('Things look okay - No serious problems were detected during the pre-flight check')

	#Exit if we are just here for config checking
        if self.verify_only:
            sys.exit(0)
	
        #self.conf.debug()
	
        #Ok, here we must check if we go on or not.
        #TODO : check OK or not
        self.pidfile = self.conf.lock_file
        self.idontcareaboutsecurity = self.conf.idontcareaboutsecurity
        self.user = self.conf.nagios_user
        self.group = self.conf.nagios_group
        self.workdir = os.path.expanduser('~'+self.user)
        
        #If we go, we must go in daemon or not
        #Check if another Scheduler is not running (with the same conf)
        self.check_parallele_run(do_replace)
                
        #If the admin don't care about security, I allow root running
        insane = not self.idontcareaboutsecurity


        #Try to change the user (not nt for the moment)
        #TODO: change user on nt
        if os.name != 'nt':
            self.change_user(insane)
        else:
            Log().log("Warning : you can't change user on this system")
        
        #Now the daemon part if need
        if is_daemon:
            self.create_daemon(do_debug=debug, debug_file=debug_file)

        Log().log("Opening of the network port")
        #Now open the daemon port for Broks and other Arbiter sends
        Pyro.config.PYRO_STORAGE = self.workdir
        Pyro.config.PYRO_COMPRESSION = 1
        Pyro.config.PYRO_MULTITHREADED = 0
        Pyro.core.initServer()
	
        Log().log("Listening on %s:%d" % (self.me.address, self.me.port))
        self.poller_daemon = Pyro.core.Daemon(host=self.me.address, port=self.me.port)
        if self.poller_daemon.port != self.me.port:
            Log().log("Error : the port %d is not free!" % self.me.port)
            sys.exit(1)

        self.ibroks = IBroks(self)
        self.uri = self.poller_daemon.connect(self.ibroks,"Broks")
        self.iarbiters = IArbiters(self)
        self.uri_arb = self.poller_daemon.connect(self.iarbiters,"ForArbiter")
        #print "The Broks Interface uri is:", self.uri


        Log().log("Configuration Loaded")

        #Main loop
        while True:
	    #If I am a spare, I wait for the master arbiter to send me
	    #true conf. When 
            if self.me.spare:
                self.wait_initial_conf()
            else:#I'm the master, I've got a conf
                self.is_master = True
                self.have_conf = True

            #Ok, now It've got a True conf, Now I wait to get too much
            #time without 
            if self.me.spare:
                print "I must wait now"
                self.wait_for_master_death()

            if self.must_run:
                #Main loop
                self.run()


    #We wait (block) for arbiter to send us conf
    def wait_initial_conf(self):
        self.have_conf = False
        print "Waiting for configuration from master"
        timeout = 1.0
        while not self.have_conf :
            socks = self.poller_daemon.getServerSockets()
            avant = time.time()
            # 'foreign' event loop
            ins, outs, exs = select.select(socks, [], [], timeout)
            if ins != []:
                for s in socks:
                    if s in ins:
                        self.poller_daemon.handleRequests()
                        print "Apres handle : Have conf?", self.have_conf
                        apres = time.time()
                        diff = apres-avant
                        timeout = timeout - diff
                        break    # no need to continue with the for loop
            else: #Timeout
                sys.stdout.write(".")
                sys.stdout.flush()
                timeout = 1.0

            if timeout < 0:
                timeout = 1.0


    #We wait (block) for arbiter to send us something
    def wait_for_master_death(self):
        print "Waiting for master death"
        timeout = 1.0
        is_master_dead = False
        self.last_master_speack = time.time()
        while not is_master_dead:
            socks = self.poller_daemon.getServerSockets()
            avant = time.time()
            # 'foreign' event loop
            ins, outs, exs = select.select(socks, [], [], timeout)
            if ins != []:
                for s in socks:
                    if s in ins:
                        self.poller_daemon.handleRequests()
                        self.last_master_speack = time.time()
                        apres = time.time()
                        diff = apres-avant
                        timeout = timeout - diff
            else: #Timeout
                sys.stdout.write(".")
                sys.stdout.flush()
                timeout = 1.0

            if timeout < 0:
                timeout = 1.0
            
            #Now check if master is die or not
            now = time.time()
            if now - self.last_master_speack > 5:
                print "Master is dead!!!"
                self.must_run = True
                is_master_dead = True


    #Main function
    def run(self):
        #Before running, I must be sure who Im I
        #The arbiters change, so we must refound the new self.me
        for arb in self.conf.arbiterlinks:
            if arb.is_me():
                self.me = arb

        Log().log("Begin to dispatch configurations to satellites")
        self.dispatcher = Dispatcher(self.conf, self.me)
        self.dispatcher.check_alive()
        self.dispatcher.check_dispatch()
        #REF: doc/shinken-conf-dispatching.png (3)
        self.dispatcher.dispatch()
        
	#Now create the external commander
        if os.name != 'nt':
          e = ExternalCommand(self.conf, 'dispatcher')
	
	#Scheduler need to know about external command to activate it 
        #if necessery
          self.load_external_command(e)
        else:
          self.fifo = None

        print "Run baby, run..."
        timeout = 1.0
        while self.must_run :
            socks = []
            daemon_sockets = self.poller_daemon.getServerSockets()
            socks.extend(daemon_sockets)
            avant = time.time()
            if self.fifo != None:
                socks.append(self.fifo)
            # 'foreign' event loop
            ins, outs, exs = select.select(socks, [], [], timeout)
            if ins != []:
                for s in socks:
                    if s in ins:
                        if s in daemon_sockets:
                            self.poller_daemon.handleRequests()
                            apres = time.time()
                            diff = apres-avant
                            timeout = timeout - diff
                            break    # no need to continue with the for loop
                        #If FIFO, read external command
                        if s == self.fifo:
                            self.external_command.read_and_interpret()
                            self.fifo = self.external_command.open()

            else:#Timeout
                self.dispatcher.check_alive()
                self.dispatcher.check_dispatch()
                #REF: doc/shinken-conf-dispatching.png (3)
                self.dispatcher.dispatch()
                self.dispatcher.check_bad_dispatch()
                #One broker is responsible for our broks,
                #we must give him our broks
                self.push_broks_to_broker()
                #send_conf_to_schedulers()
                timeout = 1.0

                print "Nb Broks send:", self.nb_broks_send
                #Log().log("Nb Broks send: %d" % self.nb_broks_send)
                self.nb_broks_send = 0
                
						
            if timeout < 0:
                timeout = 1.0



#if __name__ == '__main__':
#	p = Arbiter()
#        import cProfile
	#p.main()
#        command = """p.main()"""
#        cProfile.runctx( command, globals(), locals(), filename="var/Arbiter.profile" )




################### Process launch part
def usage(name):
    print "Shinken Arbiter Daemon, version %s, from :" % VERSION
    print "        Gabes Jean, naparuba@gmail.com"
    print "        Gerhard Lausser, Gerhard.Lausser@consol.de"
    print "Usage: %s [options] -c configfile [-c additionnal_config_file]" % name
    print "Options:"
    print " -c, --config"
    print "\tConfig file (your nagios.cfg). Multiple -c can be used, it will be like if all files was just one"
    print " -d, --daemon"
    print "\tRun in daemon mode"
    print " -r, --replace"
    print "\tReplace previous running scheduler"
    print " -h, --help"
    print "\tPrint detailed help screen"
    print " --debug"
    print "\tDebug File. Default : no use (why debug a bug free program? :) )"
    
    
    
#if __name__ == '__main__':
#	p = Shinken()
#        import cProfile
#	#p.main()
#        command = """p.main()"""
#        cProfile.runctx( command, globals(), locals(), filename="var/Shinken.profile" )







#Here we go!
if __name__ == "__main__":
    #Manage the options
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hvrdc::w", ["help", "verify-config", "replace", "daemon", "config=", "debug=", "easter"])
    except getopt.GetoptError, err:
        # print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        usage(sys.argv[0])
        sys.exit(2)
    #Default params
    config_files = []
    verify_only = False
    is_daemon = False
    do_replace = False
    debug = False
    debug_file = None
    for o, a in opts:
        if o in ("-h", "--help"):
            usage(sys.argv[0])
            sys.exit()
        elif o in ("-v", "--verify-config"):
            verify_only = True
        elif o in ("-r", "--replace"):
            do_replace = True
        elif o in ("-c", "--config"):
            config_files.append(a)
        elif o in ("-d", "--daemon"):
            is_daemon = True
        elif o in ("--debug"):
            debug = True
            debug_file = a
        else:
            print "Sorry, the option", o, a, "is unknown"
            usage(sys.argv[0])
            sys.exit()

    if len(config_files) == 0:
        print "Error : config file is need"
        usage(sys.argv[0])
        sys.exit()

    p = Arbiter(config_files, is_daemon, do_replace, verify_only, debug, debug_file)
    #Ok, now we load the config

    #p = Shinken(conf)
    #import cProfile
    p.main()
    #command = """p.main()"""
    #cProfile.runctx( command, globals(), locals(), filename="/tmp/Arbiter.profile" )

