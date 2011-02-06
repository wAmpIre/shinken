#!/usr/bin/env python
#Copyright (C) 2009-2010 :
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
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

import sys
import os
import time
import random
from Queue import Empty

from shinken.bin import VERSION
from shinken.util import to_bool
from shinken.objects import Config
from shinken.external_command import ExternalCommandManager
from shinken.dispatcher import Dispatcher
from shinken.daemon import Daemon
from shinken.log import logger
from shinken.modulesmanager import ModulesManager
from shinken.brok import Brok
from shinken.external_command import ExternalCommand
import shinken.pyro_wrapper as pyro
from shinken.pyro_wrapper import Pyro


# Interface for the other Arbiter
# It connect, and we manage who is the Master, slave etc.
# Here is a also a fnction to have a new conf from the master
class IArbiters(Pyro.core.ObjBase):
    # we keep arbiter link
    def __init__(self, arbiter):
        Pyro.core.ObjBase.__init__(self)
        self.arbiter = arbiter
        self.running_id = random.random()


    # Broker need to void it's broks?
    def get_running_id(self):
        return self.running_id


    def have_conf(self, magic_hash):
        # I've got a conf and the good one
        if self.arbiter.have_conf and self.arbiter.conf.magic_hash == magic_hash:
            return True
        else: #No conf or a bad one
            return False


    # The master Arbiter is sending us a new conf. Ok, we take it
    def put_conf(self, conf):
        self.arbiter.conf = conf
        print "Get conf:", self.arbiter.conf
        self.arbiter.have_conf = True
        print "Just after reception"
        self.arbiter.must_run = False


    # Ping? Pong!
    def ping(self):
        return None


    # the master arbiter ask me to do not run!
    def do_not_run(self):
        # If i'm the master, just FUCK YOU!
        if self.arbiter.is_master:
            print "Some fucking idiot ask me to do not run. I'm a proud master, so I'm still running"
        # Else I'm just a spare, so I listen to my master
        else:
            print "Someone ask me to do not run"
            self.arbiter.last_master_speack = time.time()
            self.arbiter.must_run = False


# Main Arbiter Class
class Arbiter(Daemon):
    properties = {}

    def __init__(self, config_files, is_daemon, do_replace, verify_only, debug, debug_file):
        
        Daemon.__init__(self, config_files[0], is_daemon, do_replace, debug, debug_file)
        
        self.config_files = config_files

        self.verify_only = verify_only

        self.broks = {}
        self.is_master = False
        self.me = None

        self.nb_broks_send = 0

        # Now tab for external_commands
        self.external_commands = []

        # to track system time change
        self.t_each_loop = time.time()


    # Use for adding things like broks
    def add(self, b):
        if isinstance(b, Brok):
            self.broks[b.id] = b
        elif isinstance(b, ExternalCommand):
            self.external_commands.append(b)
        else:
            logger.log('Warning : cannot manage object type %s (%s)' % (type(b), b))

            
    # We must push our broks to the broker
    # because it's stupid to make a crossing connexion
    # so we find the broker responbile for our broks,
    # and we send him it
    # TODO : better find the broker, here it can be dead?
    # or not the good one?
    def push_broks_to_broker(self):
        for brk in self.conf.brokers:
            # Send only if alive of course
            if brk.manage_arbiters and brk.alive:
                is_send = brk.push_broks(self.broks)
                if is_send:
                    # They are gone, we keep none!
                    self.broks = {}


    # We must take external_commands from all brokers
    def get_external_commands_from_brokers(self):
        for brk in self.conf.brokers:
            # Get only if alive of course
            if brk.alive:
                new_cmds = brk.get_external_commands()
                for new_cmd in new_cmds:
                    self.external_commands.append(new_cmd)


    # Our links to satellites can raise broks. We must send them
    def get_broks_from_satellitelinks(self):
        tabs = [self.conf.brokers, self.conf.schedulerlinks, \
                    self.conf.pollers, self.conf.reactionners]
        for tab in tabs:
            for s in tab:
                new_broks = s.get_all_broks()
                for b in new_broks:
                    self.add(b)


    # Our links to satellites can raise broks. We must send them
    def get_initial_broks_from_satellitelinks(self):
        tabs = [self.conf.brokers, self.conf.schedulerlinks, \
                    self.conf.pollers, self.conf.reactionners]
        for tab in tabs:
            for s in tab:
                b  = s.get_initial_status_brok()
                self.add(b)


    # Load the external commander
    def load_external_command(self, e):
        self.external_command = e
        self.fifo = e.open()


    # Check if our system time change. If so, change our
    def check_for_system_time_change(self):
        now = time.time()
        difference = now - self.t_each_loop
        # If we have more than 15 min time change, we need to
        # compensate it

        if abs(difference) > 900:
            self.compensate_system_time_change(difference)

        # Now set the new value for the tick loop
        self.t_each_loop = now

        # return the diff if it need, of just 0
        if abs(difference) > 900:
            return difference
        else:
            return 0


    # If we've got a system time change, we need to compensate it
    # from now, we do not do anything in fact.
    def compensate_system_time_change(self, difference):
        logger.log('Warning: A system time change of %s has been detected.  Compensating...' % difference)
        #We only need to change some value


    # We call the function of modules that got the this
    # hook function
    def hook_point(self, hook_name):
        to_del = []
        for inst in self.mod_instances:
            full_hook_name = 'hook_' + hook_name
            if hasattr(inst, full_hook_name):
                f = getattr(inst, full_hook_name)
                try :
                    print "Calling", full_hook_name, "of", inst.get_name()
                    f(self)
                except Exception, exp:
                    logger.log('The instance %s raise an exception %s. I kill it' % (inst.get_name(), str(exp)))
                    to_del.append(inst)

        #Now remove mod that raise an exception
        for inst in to_del:
            self.modules_manager.remove_instance(inst)


    # Main loop function
    def main(self):
        # Log will be broks
        for line in self.get_header():
            self.log.log(line)

        # Use to know if we must still be alive or not
        self.must_run = True

        print "Loading configuration"
        self.conf = Config()
        # The config Class must have the USERN macro
        # There are 256 of them, so we create online
        Config.fill_usern_macros()

        # REF: doc/shinken-conf-dispatching.png (1)
        buf = self.conf.read_config(self.config_files)

        raw_objects = self.conf.read_config_buf(buf)

        #### Loading Arbiter module part ####

        # First we need to get arbiters and modules first
        # so we can ask them some objects too
        self.conf.create_objects_for_type(raw_objects, 'arbiter')
        self.conf.create_objects_for_type(raw_objects, 'module')


        self.conf.early_arbiter_linking()

        # Search wich Arbiterlink I am
        for arb in self.conf.arbiterlinks:
            if arb.is_me():
                arb.need_conf = False
                self.me = arb
                print "I am the arbiter :", arb.get_name()
                print "Am I the master?", not self.me.spare
            else: #not me
                arb.need_conf = True

        # If None, there will be huge problems. The conf will be invalid
        # And we will bail out after print all errors
        if self.me != None:
            print "My own modules :"
            for m in self.me.modules:
                print m

            self.find_modules_path()

            self.modules_manager = ModulesManager('arbiter', self.modulespath, self.me.modules)
            self.modules_manager.load()
            # we request the instances without them being *started* 
            # (for these that are concerned ("external" modules):
            # we will *start* these instances after we have been daemonized (if requested)
            self.mod_instances = self.modules_manager.get_instances(False)

            # Call modules that manage this read configuration pass
            self.hook_point('read_configuration')

            # Now we ask for configuration modules if they
            # got items for us
            for inst in self.mod_instances:
                if 'configuration' in inst.properties['phases']:
                    try :
                        r = inst.get_objects()
                        types_creations = self.conf.types_creations
                        for k in types_creations:
                            (cls, clss, prop) = types_creations[k]
                            if prop in r:
                                for x in r[prop]:
                                    # test if raw_objects[k] is already set - if not, add empty array
                                    if not k in raw_objects:
                                        raw_objects[k] = []
                                    # now append the object
                                    raw_objects[k].append(x)
                                print "Added %i objects to %s from module %s" % (len(r[prop]), k, inst.get_name())
                    except Exception, exp:
                        print "The instance %s raise an exception %s. I bypass it" % (inst.get_name(), str(exp))

        ### Resume standard operations ###
        self.conf.create_objects(raw_objects)

        # Maybe conf is already invalid
        if not self.conf.conf_is_correct:
            print "***> One or more problems was encountered while processing the config files..."
            sys.exit(1)


        # Change Nagios2 names to Nagios3 ones
        self.conf.old_properties_names_to_new()

        # Create Template links
        self.conf.linkify_templates()

        # All inheritances
        self.conf.apply_inheritance()

        # Explode between types
        self.conf.explode()

        # Create Name reversed list for searching list
        self.conf.create_reversed_list()

        # Cleaning Twins objects
        self.conf.remove_twins()

        # Implicit inheritance for services
        self.conf.apply_implicit_inheritance()

        # Fill default values
        self.conf.fill_default()

        # Clean templates
        self.conf.clean_useless()

        # Pythonize values
        self.conf.pythonize()

        # Linkify objects each others
        self.conf.linkify()

        # applying dependancies
        self.conf.apply_dependancies()

        # Hacking some global parameter inherited from Nagios to create
        # on the fly some Broker modules like for status.dat parameters
        # or nagios.log one if there are no already available
        self.conf.hack_old_nagios_parameters()

        # Raise warning about curently unmanaged parameters
        self.conf.warn_about_unmanaged_parameters()

        # Exlode global conf parameters into Classes
        self.conf.explode_global_conf()

        # set ourown timezone and propagate it to other satellites
        self.conf.propagate_timezone_option()

        # Look for business rules, and create teh dep trees
        self.conf.create_business_rules()
        # And link them
        self.conf.create_business_rules_dependencies()


        # Warn about useless parameters in Shinken
        self.conf.notice_about_useless_parameters()

        # Manage all post-conf modules
        if self.me != None:
            self.hook_point('late_configuration')
        
        # Correct conf?
        self.conf.is_correct()

        #If the conf is not correct, we must get out now
        if not self.conf.conf_is_correct:
            print "Configuration is incorrect, sorry, I bail out"
            sys.exit(1)

        #Debug to see memory and objects :)
        #self.conf.dump()
        #from guppy import hpy
        #hp=hpy()
        #print hp.heap()
        #print hp.heapu()

        # Search myself as an arbiter object
        if self.me == None:
            print "Error : I cannot find my own Arbiter object, I bail out"
            print "To solve it : please change the host_name parameter in the object Arbiter"
            print "in the file shinken-specific.cfg. Thanks."
            sys.exit(1)


        # If I am a spare, I must wait a (true) conf from Arbiter Master
        self.wait_conf = self.me.spare

        # REF: doc/shinken-conf-dispatching.png (2)
        logger.log("Cutting the hosts and services into parts")
        self.confs = self.conf.cut_into_parts()

        # The conf can be incorrect here if the cut into parts see errors like
        # a realm with hosts and not schedulers for it
        if not self.conf.conf_is_correct:
            print "Configuration is incorrect, sorry, I bail out"
            sys.exit(1)

        logger.log('Things look okay - No serious problems were detected during the pre-flight check')

        # Exit if we are just here for config checking
        if self.verify_only:
            sys.exit(0)

        # Some properties need to be "flatten" (put in strings)
        # before being send, like realms for hosts for example
        # BEWARE: after the cutting part, because we stringify some properties
        self.conf.prepare_for_sending()

        logger.log("Configuration Loaded")


        # Ok, here we must check if we go on or not.
        # TODO : check OK or not
        self.pidfile = self.conf.lock_file
        self.idontcareaboutsecurity = self.conf.idontcareaboutsecurity
        self.user = self.conf.shinken_user
        self.group = self.conf.shinken_group
        self.workdir = os.path.expanduser('~'+self.user)

        ##  We need to set self.host & self.port to be used by do_daemon_init_and_start
        self.host = self.me.address
        self.port = self.me.port
        self.do_daemon_init_and_start(self.conf)

        # ok we are now fully daemon (if requested)
        # now we can start our "external" modules (if any) :
        self.modules_manager.init_and_start_instances()
        self.mod_instances = self.modules_manager.instances

        self.iarbiters = IArbiters(self)

        self.uri_arb = pyro.register(self.daemon, self.iarbiters, "ForArbiter")

        ## And go for the main loop
        self.do_mainloop()

        
    def do_loop_turn(self):
        # If I am a spare, I wait for the master arbiter to send me
        # true conf. When
        if self.me.spare:
            self.wait_initial_conf()
        else: # I'm the master, I've got a conf
            self.is_master = True
            self.have_conf = True

        #Ok, now It've got a True conf, Now I wait to get too much
        #time without
        if self.me.spare:
            print "I must wait now"
            self.wait_for_master_death()

        if self.must_run:
            # Main loop
            self.run()


    # Get 'objects' from external modules
    # It can be used for get external commands for example
    def get_objects_from_from_queues(self):
        for f in self.modules_manager.get_external_from_queues():
            print "Groking from module instance %s" % f
            while True:
                try:
                    o = f.get(block=False)
                    print "Got object :", o
                    self.add(o)
                except Empty:
                    break



    # We wait (block) for arbiter to send us conf
    def wait_initial_conf(self):
        self.have_conf = False
        print "Waiting for configuration from master"
        timeout = 1.0
        while not self.have_conf and not self.interrupted:
            avant = time.time()
            socks = pyro.get_sockets(self.daemon)

            # 'foreign' event loop
            ins = self.get_socks_activity(socks, timeout)

            # Manage a possible time change (our avant will be change with the diff)
            diff = self.check_for_system_time_change()
            avant += diff

            if ins != []:
                for s in socks:
                    if s in ins:
                        pyro.handleRequests(self.daemon, s)
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

        if self.interrupted:
            self.request_stop()


    # We wait (block) for arbiter to send us something
    def wait_for_master_death(self):
        print "Waiting for master death"
        timeout = 1.0
        is_master_dead = False
        self.last_master_speack = time.time()
        while not is_master_dead and not self.interrupted:

            avant = time.time()
            
            socks = pyro.get_sockets(self.daemon)
            ins = self.get_socks_activity(socks, timeout)

            # Manage a possible time change (our avant will be change with the diff)
            diff = self.check_for_system_time_change()
            avant += diff

            if ins != []:
                for s in socks:
                    if s in ins:
                        pyro.handleRequests(self.daemon, s)
                        self.last_master_speack = time.time()
                        apres = time.time()
                        diff = apres-avant
                        timeout = timeout - diff
            else: # Timeout
                sys.stdout.write(".")
                sys.stdout.flush()
                timeout = 1.0

            if timeout < 0:
                timeout = 1.0

            #Now check if master is dead or not
            now = time.time()
            if now - self.last_master_speack > 5:
                print "Master is dead!!!"
                self.must_run = True
                is_master_dead = True



    def do_stop(self):
        print "Stopping all network connexions"
        self.daemon.shutdown(True)
        self.modules_manager.clear_instances()


    # Main function
    def run(self):
        # Before running, I must be sure who am I
        # The arbiters change, so we must refound the new self.me
        for arb in self.conf.arbiterlinks:
            if arb.is_me():
                self.me = arb

        logger.log("Begin to dispatch configurations to satellites")
        self.dispatcher = Dispatcher(self.conf, self.me)
        self.dispatcher.check_alive()
        self.dispatcher.check_dispatch()
        # REF: doc/shinken-conf-dispatching.png (3)
        self.dispatcher.dispatch()

        # Now we can get all initial broks for our satellites
        self.get_initial_broks_from_satellitelinks()

        # Now create the external commander
        if os.name != 'nt':
            e = ExternalCommandManager(self.conf, 'dispatcher')

            # Arbiter need to know about external command to activate it
            # if necessary
            self.load_external_command(e)
        else:
            self.fifo = None

        print "Run baby, run..."
        timeout = 1.0
        while self.must_run and not self.interrupted:
            socks = []
            daemon_sockets = pyro.get_sockets(self.daemon)
            socks.extend(daemon_sockets)
            avant = time.time()
            if self.fifo != None:
                socks.append(self.fifo)
            # 'foreign' event loop
            ins = self.get_socks_activity(socks, timeout)

            # Manage a possible time change (our avant will be change with the diff)
            diff = self.check_for_system_time_change()
            avant += diff

            if ins != []:
                for s in socks:
                    if s in ins:
                        if s in daemon_sockets:
                            pyro.handleRequests(self.daemon, s)
                            apres = time.time()
                            diff = apres-avant
                            timeout = timeout - diff
                            break    # no need to continue with the for loop
                        # If FIFO, read external command
                        if s == self.fifo:
                            ext_cmds = self.external_command.get()
                            if ext_cmds:
                                for ext_cmd in ext_cmds:
                                    self.external_commands.append(ext_cmd)
                            else:
                                self.fifo = self.external_command.open()

            else: # Timeout
                # Call modules that manage a starting tick pass
                self.hook_point('tick')
                
                self.dispatcher.check_alive()
                self.dispatcher.check_dispatch()
                # REF: doc/shinken-conf-dispatching.png (3)
                self.dispatcher.dispatch()
                self.dispatcher.check_bad_dispatch()

                # Now get things from our module instances
                self.get_objects_from_from_queues()

                # Maybe our satellites links raise new broks. Must reap them
                self.get_broks_from_satellitelinks()

                # One broker is responsible for our broks,
                # we must give him our broks
                self.push_broks_to_broker()
                self.get_external_commands_from_brokers()
                # send_conf_to_schedulers()
                timeout = 1.0

                print "Nb Broks send:", self.nb_broks_send
                self.nb_broks_send = 0

                # Now send all external commands to schedulers
                for ext_cmd in self.external_commands:
                    self.external_command.resolve_command(ext_cmd)
                # It's send, do not keep them
                # TODO: check if really send. Queue by scheduler?
                self.external_commands = []

            if timeout < 0:
                timeout = 1.0



################### Process launch part
def usage(name):
    print "Shinken Arbiter Daemon, version %s, from :" % VERSION
    print "        Gabes Jean, naparuba@gmail.com"
    print "        Gerhard Lausser, Gerhard.Lausser@consol.de"
    print "        Gregory Starck, g.starck@gmail.com"
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

