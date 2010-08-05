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


#For the Shinken application, I try to respect
#The Zen of Python, by Tim Peters. It's just some
#very goods ideas that make Python programming very fun
#and efficient. If it's good for Python, it must be good for
#Shinken. :)
#
#
#
#Beautiful is better than ugly.
#Explicit is better than implicit.
#Simple is better than complex.
#Complex is better than complicated.
#Flat is better than nested.
#Sparse is better than dense.
#Readability counts.
#Special cases aren't special enough to break the rules.
#Although practicality beats purity.
#Errors should never pass silently.
#Unless explicitly silenced.
#In the face of ambiguity, refuse the temptation to guess.
#There should be one-- and preferably only one --obvious way to do it.
#Although that way may not be obvious at first unless you're Dutch.
#Now is better than never.
#Although never is often better than *right* now.
#If the implementation is hard to explain, it's a bad idea.
#If the implementation is easy to explain, it may be a good idea.
#Namespaces are one honking great idea -- let's do more of those!


#This class is the app for scheduling
#it create the scheduling object after listen for arbiter
#for a conf. It listen for arbiter even after the scheduler is launch.
#if a new conf is received, the scheduler is stopped
#and a new one is created.
#The scheduler create list of checks and actions for poller
#and reactionner.
import os
import time
import sys
import platform
import select
import random
import getopt



#We know that a Python 2.5 or Python3K will fail.
#We can say why and quit.
python_version = platform.python_version_tuple()

## Make sure people are using Python 2.5 or higher
if int(python_version[0]) == 2 and int(python_version[1]) < 6:
    print "Shinken require as a minimum Python 2.6.x, sorry"
    sys.exit(1)

if int(python_version[0]) == 3:
    print "Shinken is not yet compatible with Python3k, sorry"
    sys.exit(1)

#DBG for Pyro 4
sys.path.insert(0, '.')


try:
    import shinken.pyro_wrapper    
except ImportError:
    print "Shinken require the Python Pyro module. Please install it."
    sys.exit(1)

Pyro = shinken.pyro_wrapper.Pyro

#Try to load shinken lib.
#Maybe it's not in our python path, so we detect it
#it so (it's a untar install) we add .. in the path

try :
    from shinken.util import to_bool
    my_path = os.path.abspath(sys.modules['__main__'].__file__)
    elts = os.path.dirname(my_path).split(os.sep)[:-1]
    elts.append('shinken')
    sys.path.append(os.sep.join(elts))
except ImportError:
    #Now add in the python path the shinken lib
    #if we launch it in a direct way and
    #the shinken is not a python lib
    my_path = os.path.abspath(sys.modules['__main__'].__file__)
    elts = os.path.dirname(my_path).split(os.sep)[:-1]
    sys.path.append(os.sep.join(elts))
    elts.append('shinken')
    sys.path.append(os.sep.join(elts))


from shinken.scheduler import Scheduler
from shinken.config import Config
from shinken.macroresolver import MacroResolver
from shinken.external_command import ExternalCommand
from shinken.daemon import Daemon#create_daemon, check_parallel_run, change_user
from shinken.util import to_int, to_bool


VERSION = "0.2"



#Interface for Workers
#They connect here and see if they are still OK with
#our running_id, if not, they must drop their checks
#in progress
class IChecks(Pyro.core.ObjBase):
    #we keep sched link
    #and we create a running_id so poller and
    #reactionner know if we restart or not
    def __init__(self, sched):
        Pyro.core.ObjBase.__init__(self)
        self.sched = sched
        self.running_id = random.random()


    #poller or reactionner is asking us our running_id
    def get_running_id(self):
        return self.running_id

		
    #poller or reactionner ask us actions
    def get_checks(self , do_checks=False, do_actions=False, poller_tags=[]):
        #print "We ask us checks"
        res = self.sched.get_to_run_checks(do_checks, do_actions, poller_tags)
        #print "Sending %d checks" % len(res)
        self.sched.nb_checks_send += len(res)
        return res

	
    #poller or reactionner are putting us results
    def put_results(self, results):
        nb_received = len(results)
        self.sched.nb_check_received += nb_received
        print "Received %d results" % nb_received
        self.sched.waiting_results.extend(results)
		
        #for c in results:
        #self.sched.put_results(c)
        return True



#Interface for Brokers
#They connect here and get all broks (data for brokers)
#datas must be ORDERED! (initial status BEFORE uodate...)
class IBroks(Pyro.core.ObjBase):
    #we keep sched link
    def __init__(self, sched):
        Pyro.core.ObjBase.__init__(self)
        self.sched = sched
        self.running_id = random.random()


    #Broker need to void it's broks?
    def get_running_id(self):
        return self.running_id

		
    #poller or reactionner ask us actions
    def get_broks(self):
        #print "We ask us broks"
        res = self.sched.get_broks()
        #print "Sending %d broks" % len(res)#, res
        self.sched.nb_broks_send += len(res)
        #we do not more have a full broks in queue
        self.sched.has_full_broks = False
        return res

    #A broker is a new one, if we do not have
    #a full broks, we clean our broks, and
    #fill it with all new values
    def fill_initial_broks(self):
        if not self.sched.has_full_broks:
            self.sched.broks.clear()
            self.sched.fill_initial_broks()
            

    #Ping? Pong!
    def ping(self):
        return None


#Interface for Arbiter, our big MASTER
#We ask him a conf and after we listen for him.
#HE got user entry, so we must listen him carefully
#and give information he want, maybe for another scheduler
class IForArbiter(Pyro.core.ObjBase):
    def __init__(self, app):
        Pyro.core.ObjBase.__init__(self)
        self.app = app
        self.running_id = random.random()

    #very useful?
    def get_running_id(self):
        return self.running_id


    #use full too?
    def get_info(self, type, ref, prop, other):
        return self.app.sched.get_info(type, ref, prop, other)


    #arbiter is send us a external coomand.
    #it can send us global command, or specific ones
    def run_external_command(self, command):
        self.app.sched.run_external_command(command)


    #Arbiter is sending us a new conf. We check if we do not already have it.
    #If not, we take it, and if app has a scheduler, we ask it to die,
    #so the new conf  will be load, and a new scheduler created
    def put_conf(self, conf):
        if not self.app.have_conf or self.app.conf.magic_hash != conf.magic_hash:
            self.app.conf = conf
            print "Get conf:", self.app.conf
            self.app.have_conf = True
            print "Have conf?", self.app.have_conf
            print "Just apres reception"
		
            #if app already have a scheduler, we must say him to 
            #DIE Mouahahah
            #So It will quit, and will load a new conf (and create a brand new scheduler)
            if hasattr(self.app, "sched"):
                self.app.sched.die()
			

    #Arbiter want to know if we are alive
    def ping(self):
        return True

    #Use by arbiter to know if we have a conf or not
    #can be usefull if we must do nothing but 
    #we are not because it can KILL US! 
    def have_conf(self):
        return self.app.have_conf


    #Call by arbiter if it thinks we are running but we must do not (like
    #if I was a spare that take a conf but the master returns, I must die
    #and wait a new conf)
    #Us : No please...
    #Arbiter : I don't care, hasta la vista baby!
    #Us : ... <- Nothing! We are die! you don't follow 
    #anything or what??
    def wait_new_conf(self):
        print "Arbiter want me to wait a new conf"
        self.app.have_conf = False
        if hasattr(self.app, "sched"):
            self.app.sched.die()


#Tha main app class
class Shinken(Daemon):
    #default_port = 7768

    properties = {
        'workdir' : {'default' : '/usr/local/shinken/var', 'pythonize' : None, 'path' : True},
        'pidfile' : {'default' : '/usr/local/shinken/var/schedulerd.pid', 'pythonize' : None, 'path' : True},
        'port' : {'default' : '7768', 'pythonize' : to_int},
        'host' : {'default' : '0.0.0.0', 'pythonize' : None},
        'user' : {'default' : 'shinken', 'pythonize' : None},
        'group' : {'default' : 'shinken', 'pythonize' : None},
        'idontcareaboutsecurity' : {'default' : '0', 'pythonize' : to_bool}
        }

    #Create the shinken class:
    #Create a Pyro server (port = arvg 1)
    #then create the interface for arbiter
    #Then, it wait for a first configuration
    def __init__(self, config_file, is_daemon, do_replace, debug, debug_file):
        self.print_header()
        
        #From daemon to manage signal. Call self.manage_signal if
        #exists, a dummy function otherwise
        self.set_exit_handler()

        self.config_file = config_file
        #Read teh config file if exist
        #if not, default properties are used
        self.parse_config_file()

        if config_file != None:
            #Some paths can be relatives. We must have a full path by taking
            #the config file by reference
            self.relative_paths_to_full(os.path.dirname(config_file))

        #Check if another Scheduler is not running (with the same conf)
        self.check_parallel_run(do_replace)
                
        #If the admin don't care about security, I allow root running
        insane = not self.idontcareaboutsecurity

        #Try to change the user (not nt for the moment)
        #TODO: change user on nt
        if os.name != 'nt':
            self.change_user(insane)
        else:
            print "Sorry, you can't change user on this system"
        
        #Now the daemon part if need
        if is_daemon:
            self.create_daemon(do_debug=debug, debug_file=debug_file)


        #TODO : signal managment
        #atexit.register(unlink, pidfile=conf['pidfile'])

        #Config Class must be filled with USERN Macro
        Config.fill_usern_macros()
		
        #create the server
        print "Using working directory : %s" % os.path.abspath(self.workdir)
        Pyro.config.PYRO_STORAGE = self.workdir
        Pyro.config.PYRO_COMPRESSION = 1
        Pyro.config.PYRO_MULTITHREADED = 0

        self.poller_daemon = shinken.pyro_wrapper.init_daemon(self.host, self.port)

        print "Listening on:", self.host, ":", self.port

        #Now the interface
        i_for_arbiter = IForArbiter(self)
        
        self.uri2 = shinken.pyro_wrapper.register(self.poller_daemon, i_for_arbiter, "ForArbiter")

        print "The Arbiter Interface is at:", self.uri2
		
        #Ok, now the conf
        self.must_run = True
        self.wait_initial_conf()
        print "Ok we've got conf"

        #Interface for Broks and Checks
        self.ichecks = None
        self.ibroks = None


    #Manage signal function
    #TODO : manage more than just quit
    #Frame is just garbage
    def manage_signal(self, sig, frame):
        print "\nExiting with signal", sig
        self.poller_daemon.shutdown(True)
        sys.exit(0)

		

    #We wait (block) for arbiter to send us conf
    def wait_initial_conf(self):

        self.have_conf = False
        print "Waiting for initial configuration"
        timeout = 1.0
        while not self.have_conf :
            socks = shinken.pyro_wrapper.get_sockets(self.poller_daemon)
            
            avant = time.time()
            # 'foreign' event loop
            ins, outs, exs = select.select(socks, [], [], timeout)
            if ins != []:
                for s in socks:
                    if s in ins:
                        #Cal the wrapper to manage the good 
                        #handleRequests call of daemon
                        shinken.pyro_wrapper.handleRequests(self.poller_daemon, s)
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


    #OK, we've got the conf, now we load it
    #and launch scheduler with it
    #we also create interface for poller and reactionner
    def load_conf(self):
        #create scheduler with ref of our daemon
        self.sched = Scheduler(self.poller_daemon)
		
        #give it an interface
        #But first remove previous interface if exists
        if self.ichecks != None:
            print "Deconnecting previous Check Interface from daemon"
            shinken.pyro_wrapper.unregister(self.poller_daemon, self.ichecks)

        #Now create and connect it
        self.ichecks = IChecks(self.sched)
        self.uri = shinken.pyro_wrapper.register(self.poller_daemon, self.ichecks, "Checks")
        print "The Checks Interface uri is:", self.uri
		
        #Same for Broks
        if self.ibroks != None:
            print "Deconnecting previous Broks Interface from daemon"
            shinken.pyro_wrapper.unregister(self.poller_daemon, self.ibroks)

        #Create and connect it
        self.ibroks = IBroks(self.sched)
        self.uri2 = shinken.pyro_wrapper.register(self.poller_daemon, self.ibroks, "Broks")
        print "The Broks Interface uri is:", self.uri2

        print "Loading configuration"
        self.conf.explode_global_conf()
        #we give sched it's conf
        self.sched.load_conf(self.conf)

        self.conf.is_correct()


        #Creating the Macroresolver Class & unique instance
        m = MacroResolver()
        m.init(self.conf)

        #self.conf.dump()
        #self.conf.quick_debug()
		
        #Now create the external commander
        #it's a applyer : it role is not to dispatch commands,
        #but to apply them
        e = ExternalCommand(self.conf, 'applyer')

        #Scheduler need to know about external command to 
        #activate it if necessery
        self.sched.load_external_command(e)
		
        #External command need the sched because he can raise checks
        e.load_scheduler(self.sched)


    #our main function, launch after the init
    def main(self):
        #ok, if we are here, we've got the conf
        self.load_conf()
		
        print "Configuration Loaded"
        while self.must_run:
            self.sched.run()
            #Ok, we quit scheduler, but maybe it's just for
            #reloading our configuration
            if self.must_run:
                if self.have_conf:
                    self.load_conf()
                else:
                    self.wait_initial_conf()
                    self.load_conf()
				

################### Process launch part
def usage(name):
    print "Shinken Scheduler Daemon, version %s, from :" % VERSION
    print "        Gabes Jean, naparuba@gmail.com"
    print "        Gerhard Lausser, Gerhard.Lausser@consol.de"
    print "Usage: %s [options] [-c configfile]" % name
    print "Options:"
    print " -c, --config"
    print "\tConfig file."
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
        opts, args = getopt.getopt(sys.argv[1:], "hrdc::w", ["help", "replace", "daemon", "config=", "debug=", "easter"])
    except getopt.GetoptError, err:
        # print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        usage(sys.argv[0])
        sys.exit(2)
    #Default params
    config_file = None
    is_daemon = False
    do_replace = False
    debug = False
    debug_file = None
    for o, a in opts:
        if o in ("-h", "--help"):
            usage(sys.argv[0])
            sys.exit()
        elif o in ("-r", "--replace"):
            do_replace = True
        elif o in ("-c", "--config"):
            config_file = a
        elif o in ("-d", "--daemon"):
            is_daemon = True
        elif o in ("--debug"):
            debug = True
            debug_file = a
        else:
            print "Sorry, the option", o, a, "is unknown"
            usage(sys.argv[0])
            sys.exit()

    p = Shinken(config_file, is_daemon, do_replace, debug, debug_file)
    #Ok, now we load the config

    #p = Shinken(conf)
    #import cProfile
    p.main()
    #command = """p.main()"""
    #cProfile.runctx( command, globals(), locals(), filename="/tmp/Shinken.profile" )

