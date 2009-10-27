#!/usr/bin/python
#Copyright (C) 2009 Gabes Jean, naparuba@gmail.com
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


#This class is an interface for reactionner and poller
#The satallite listen configuration from Arbiter in a port (first argument)
#the configuration gived by arbiter is schedulers where actionner will 
#take actions.
#When already launch and have a conf, actionner still listen to arbiter
#(one a timeout)
#if arbiter whant it to have a new conf, satellite forgot old schedulers
#(and actions into)
#take new ones and do the (new) job.

from Queue import Empty
from multiprocessing import Queue
import time
import sys
import Pyro.core
import select

from message import Message
from worker import Worker
#from util import get_sequence


#Interface for Arbiter, our big MASTER
#It put us our conf
class IForArbiter(Pyro.core.ObjBase):
	#We keep app link because we are just here for it
	def __init__(self, app):
		Pyro.core.ObjBase.__init__(self)
		self.app = app
		self.schedulers = app.schedulers


	#function called by arbiter for giving us our conf
	#conf must be a dict with:
	#'schedulers' : schedulers dict (by id) with address and port
	def put_conf(self, conf):
		self.app.have_conf = True
		print "Sending us ", conf
		#If we've got something in the schedulers, we do not want it anymore
		self.schedulers.clear()
		for sched_id in conf['schedulers'] :
			s = conf['schedulers'][sched_id]
			self.schedulers[sched_id] = s
			uri = "PYROLOC://%s:%d/Checks" % (s['address'], s['port'])
			self.schedulers[sched_id]['uri'] = uri
			self.schedulers[sched_id]['verifs'] = {}
			self.schedulers[sched_id]['running_id'] = 0
			#We cannot reinit connexions because this code in in a thread, and
			#pyro do not allow thread to create new connexions...
			#So we do it just after.
		print "We have our schedulers :", self.schedulers
		

	#Use for arbiter to know if we are alive
	def ping(self):
		print "We ask us for a ping"
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


#Our main APP class
class Satellite:
	def __init__(self):
		#Bool to know if we have received conf from arbiter
		self.have_conf = False
		self.s = Queue() #Global Master -> Slave
		self.m = Queue() #Slave -> Master

		#Ours schedulers
		self.schedulers = {}

		self.workers = {} #dict of active workers
		self.newzombies = [] #list of fresh new zombies, will be join the next loop
		self.zombies = [] #list of quite old zombies, will be join now
		


	#initialise or re-initialise connexion with scheduler
	def pynag_con_init(self, id):
		print "init de connexion avec", self.schedulers[id]['uri']
		running_id = self.schedulers[id]['running_id']
		self.schedulers[id]['con'] = Pyro.core.getProxyForURI(self.schedulers[id]['uri'])
		#timeout of 5 s
		try:
			self.schedulers[id]['con']._setTimeout(5)
			new_run_id = self.schedulers[id]['con'].get_running_id()
		except Pyro.errors.ProtocolError, exp:
			print exp
			return
		except Pyro.errors.NamingError, exp:
			print "Scheduler is not initilised", exp
			self.schedulers[id]['con'] = None
			return
		except PicklingError, exp:
			print "Scheduler is not initilised", exp
			self.schedulers[id]['con'] = None
			return
		except KeyError, exp:
                        print "Scheduler is not initilised", exp
                        self.schedulers[id]['con'] = None
                        return

		#The schedulers have been restart : it has a new run_id.
		#So we clear all verifs, they are obsolete now.
		if self.schedulers[id]['running_id'] != 0 and new_run_id != running_id:
			self.schedulers[id]['verifs'].clear()
		self.schedulers[id]['running_id'] = new_run_id
		#We do not need result of put_results, there is no one
		try:
			self.schedulers[id]['con']._setOneway('put_results')
		except KeyError, exp:
                        print "Scheduler is not initilised", exp
                        self.schedulers[id]['con'] = None
                        return

		print "Connexion OK"


        #Manage messages from Workers
	def manage_msg(self, msg):
		#Ok, a worker whant to die. It's sad, but we must kill him!!!
		if msg.get_type() == 'IWantToDie':
			zombie = msg.get_from()
			print "Got a ding wish from ", zombie
			self.workers[zombie].join()
		#Ok, it's a result. We get it, and fill verifs of the good sched_id

		if msg.get_type() == 'Result':
			id = msg.get_from()
			self.workers[id].reset_idle()
			chk = msg.get_data()
			sched_id = chk.sched_id
			chk.set_status('waitforhomerun')
			self.schedulers[sched_id]['verifs'][chk.get_id()] = chk


        #Return the chk to scheduler and clean them
	def manage_return(self):
		#Fot all schedulers, we check for waitforhomerun and we send back results
		for sched_id in self.schedulers:
			ret = []
			verifs = self.schedulers[sched_id]['verifs']
                        #Get the id to return to shinken, so after make 
			#a big array with only them
			id_to_return = [elt for elt in verifs.keys() if verifs[elt].get_status() == 'waitforhomerun']
			for id in id_to_return:
				try:
					v = verifs[id]
				#We got v without the sched_id prop, so we
				#remove it before resent it.
					del v.sched_id
					ret.append(v)
				
				except AttributeError as exp:
					print exp
			#Now ret have all verifs, we can return them
			if ret is not []:
				try:
					con = self.schedulers[sched_id]['con']
					if con is not None:#None = not initialized
						con.put_results(ret)
				except Pyro.errors.ProtocolError:
					self.pynag_con_init(sched_id)
					return
				except AttributeError as exp: #the scheduler must  not be initialized
					print exp
				except KeyError as exp: # sched is gone
                                        print exp
                                        self.pynag_con_init(sched_id)
                                        return
				except Exception,x:
					print ''.join(Pyro.util.getPyroTraceback(x))
					sys.exit(0)
        
			#We clean ONLY if the send is OK
			for id in id_to_return:
				del verifs[id]


	#Use to wait conf from arbiter.
	#It send us conf in our daemon. It put the have_conf prop
	#if he send us something
	#(it can just do a ping)
	def wait_for_initial_conf(self):
		print "Waiting for initial configuration"
		timeout = 1.0
		#Arbiter do not already set our have_conf param
		while not self.have_conf :
			socks = self.daemon.getServerSockets()
			avant = time.time()
			ins,outs,exs = select.select(socks,[],[],timeout)   # 'foreign' event loop
			if ins != []:
				for sock in socks:
					if sock in ins:
						self.daemon.handleRequests()
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

				
	#The arbiter can resent us new conf in the daemon port.
	#We do not want to loose time about it, so it's not a bloking 
	#wait, timeout = 0s
	#If it send us a new conf, we reinit the connexions of all schedulers
	def watch_for_new_conf(self):
		timeout_daemon = 0.0
		socks = self.daemon.getServerSockets()
		# 'foreign' event loop
		ins,outs,exs = select.select(socks,[],[],timeout_daemon)
		if ins != []:
			for sock in socks:
				if sock in ins:
					self.daemon.handleRequests()
					for sched_id in self.schedulers:
						self.pynag_con_init(sched_id)


	#Create and launch a new worker, and put it into self.workers
	#It can be mortal or not
	def create_and_launch_worker(self, mortal=True):
		w = Worker(1, self.s, self.m, mortal=mortal)
		self.workers[w.id] = w#Worker(id, self.s, self.m, mortal=True)
		print "Allocate : ", w.id
		self.workers[w.id].start()


	#Workers are process. We need to clean them some time (see zombie part)
	#Here we create new workers if the queue load (len of verifs) is too long
	#here it's > 80% of workers
	def adjust_worker_number_by_load(self):
            nb_queue = 0 # Len of actions in queue status, so the working queue
            for sched_id in self.schedulers:
                verifs = self.schedulers[sched_id]['verifs']
                tmp_nb_queue = len([elt for elt in verifs.keys() if verifs[elt].get_status() == 'queue'])
                nb_queue += tmp_nb_queue
                nb_waitforhomerun = len([elt for elt in verifs.keys() if verifs[elt].get_status() == 'waitforhomerun'])
                print '[%d]Stats : Workers:%d Check %d (Queued:%d ReturnWait:%d)' % (sched_id, len(self.workers), len(verifs), tmp_nb_queue, nb_waitforhomerun)            
		#We add new worker if the queue is > 80% of the worker number
            while nb_queue > 0.8 * len(self.workers) and len(self.workers) < 30:
                self.create_and_launch_worker()


	#We get new actions from schedulers, we create a Message ant we 
	#put it in the s queue (from master to slave)
	def get_new_actions(self):
		new_checks = []
		#We check for new check in each schedulers and put the result in new_checks
		for sched_id in self.schedulers:
			try:
				con = self.schedulers[sched_id]['con']
				if con is not None: #None = not initilized
                                        #Here are the differences between a 
					#poller and a reactionner:
                                        #Poller will only do checks,
					#reactionner do actions
                                        do_checks = self.__class__.do_checks
                                        do_actions = self.__class__.do_actions
					tmp_verifs = con.get_checks(do_checks=do_checks, do_actions=do_actions)
					print "Ask actions to", sched_id, "got", len(tmp_verifs)
					#print "We've got new verifs" , tmp_verifs
					for v in tmp_verifs:
						v.sched_id = sched_id
					new_checks.extend(tmp_verifs)
				else: #no con? make the connexion
					self.pynag_con_init(sched_id)
                        #Ok, con is not know, so we create it
			except KeyError as exp:
				self.pynag_con_init(sched_id)
			except Pyro.errors.ProtocolError as exp:
				print exp
				#we reinitialise the ccnnexion to pynag
				self.pynag_con_init(sched_id)
                        #scheduler must not be initialized
			except AttributeError as exp:
				print exp
                        #scheduler must not have checks
			except Pyro.errors.NamingError as exp:
				print exp
			# What the F**k? We do not know what happenned,
			#so.. bye bye :)
			except Exception,x:
				print ''.join(Pyro.util.getPyroTraceback(x))
				sys.exit(0)
		#Ok, we've got new actions in new_checks
		#so we put them in queue state and we put in in the
		#working queue for workers
		for chk in new_checks:
			chk.set_status('queue')
			verifs = self.schedulers[chk.sched_id]['verifs']
			id = chk.get_id()
			verifs[id] = chk
			msg = Message(id=0, type='Do', data=verifs[id])
			self.s.put(msg)


	#Main function, will loop forever
	def main(self):
                #Daemon init
		Pyro.core.initServer()

		#Let the user give us a port, if not, take the default one
		if len(sys.argv) == 2:
			self.port = int(sys.argv[1])
		else:
			self.port = self.__class__.default_port
		print "Port:", self.port

		self.daemon = Pyro.core.Daemon(port=self.port)
		#If the port is not free, pyro take an other. I don't like that!
		if self.daemon.port != self.port:
			print "Sorry, the port %d was not free" % self.port
			sys.exit(1)
		self.uri2 = self.daemon.connect(IForArbiter(self),"ForArbiter")

                #We wait for initial conf
		self.wait_for_initial_conf()

                #Connexion init with PyNag server
		for sched_id in self.schedulers:
			self.pynag_con_init(sched_id)

                #Allocate Mortal Threads
		for i in xrange(1, 5):
			self.create_and_launch_worker() #create mortal worker

		#Now main loop
		i = 0
		timeout = 1.0
		while True:
			i = i + 1
			if not i % 50:
				print "Loop ", i
			begin_loop = time.time()

			#Maybe the arbiter ask us to wait for a new conf
			#If true, we must restart all...
			if self.have_conf == False:
				self.wait_for_initial_conf()
				for sched_id in self.schedulers:
					self.pynag_con_init(sched_id)

			#Now we check if arbiter speek to us in the daemon. If so, we listen for it
			#When it push us conf, we reinit connexions
			self.watch_for_new_conf()
			
			try:
				#print "Timeout", timeout
				msg = self.m.get(timeout=timeout)
				after = time.time()
				timeout -= after-begin_loop

                                #Manager the msg like check return
				self.manage_msg(msg)
            
                                #We add the time pass on the workers'idle time
				for id in self.workers:
					self.workers[id].add_idletime(after-begin_loop)

				if timeout < 0: #for go in timeout
					raise Empty
					
			except Empty as exp: #Time out Part
				after = time.time()
				timeout = 1.0
				
                                #We join (old)zombies and we move new ones
				#in the old list
				for id in self.zombies:
					self.workers[id].join()
					del self.workers[id]
				#We switch so zombie will be kill, and new
				#ones wil go in newzombies
				self.zombies = self.newzombies
				self.newzombies = []

				#Maybe we do not have enouth workers, we check for it
				#and launch new ones if need
				self.adjust_worker_number_by_load()
                
				#Now we can get new actions from schedulers
				self.get_new_actions()
				
                                #We send all finished checks
				self.manage_return()
            
				#We add the time pass on the workers
				for id in self.workers:
					self.workers[id].add_idletime(after-begin_loop)
            
				delworkers = []
                                #We look for cleaning workers
				for id in self.workers:
					if self.workers[id].is_killable():
						msg = Message(id=0, type='Die')
						self.workers[id].send_message(msg)
						self.workers[id].set_zombie()
						delworkers.append(id)
				#Cleaning the workers
				for id in delworkers:
					self.newzombies.append(id)

