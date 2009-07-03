from multiprocessing import Process, Queue
#import Queue
import time
import sys
#import random
import Pyro.core
from message import Message
#from check import Check
from worker import Worker
from util import get_sequence



s = Queue() #Global Master -> Slave
m = Queue() #Slave -> Master

workers = {} #dict of active workers
newzombies = [] #list of fresh new zombies, will be join the next loop
zombies = [] #list of quite old zombies, will be join now

request_checks = None #Pyro.core.getProxyForURI("PYROLOC://localhost:7766/Checks")
running_id = 0

verifs = {}

#Seq id for workers
seq_worker = get_sequence()
#seq_verif = get_sequence()


#initialise or re-initialise connexion with scheduler
#Check if pynag running id is still the same (just a connexion lost) or change
# so checks are bad
def scheduler_con_init():
    global request_checks
    global running_id
    global verifs
    
    request_checks = Pyro.core.getProxyForURI("PYROLOC://localhost:7768/Checks")
    try:
        new_run_id = request_checks.get_running_id()
    except Pyro.errors.ProtocolError, exp:
        print exp
        return
    if running_id != 0 and new_run_id != running_id:
        verifs.clear()
    running_id = new_run_id


#Manage messages from Workers
def manage_msg(msg):
    global zombie
    global workers
    
    if msg.get_type() == 'IWantToDie':
        zombie = msg.get_from()
        print "Got a ding wish from ",zombie
        workers[zombie].join()
    
    if msg.get_type() == 'Result':
        id = msg.get_from()
        workers[id].reset_idle()
        chk = msg.get_data()
        #print "Get result from worker", chk
        chk.set_status('waitforhomerun')
        verifs[chk.get_id()] = chk


#Return the chk to pynag and clean them
def manage_return():
    global verifs
    global request_checks
    ret = []
    #Get the id to return to pynag, so after make a big array with only them
    id_to_return = [elt for elt in verifs.keys() if verifs[elt].get_status() == 'waitforhomerun']
    #print "Check in progress:", verifs.values()
    for id in id_to_return:
        ret.append(verifs[id])
        #del verifs[id]

    try:
        request_checks.put_results(ret)
        #We clean ONLY if the send is OK
    except Pyro.errors.ProtocolError:
        scheduler_con_init()
        return
    except Exception,x:
        print ''.join(Pyro.util.getPyroTraceback(x))
        sys.exit(0)


    for id in id_to_return:
            del verifs[id]


if __name__ == '__main__':

    #Connexion init with PyNag server
    scheduler_con_init()

    #Allocate Mortal Threads
    for i in xrange(1, 5):
        id=seq_worker.next()
        print "Allocate : ",id
        workers[id]=Worker(id, s, m, mortal=True)
        workers[id].start()
    
    i = 0
    timeout = 1.0
    while True:
        i = i + 1
        if not i % 50:
            print "Loop ",i
        begin_loop = time.time()

        #print "Timeout", timeout
            
        try:
            msg = m.get(timeout=timeout)
            after = time.time()
            timeout -= after-begin_loop
            
            #Manager the msg like check return
            manage_msg(msg)
            
            #We add the time pass on the workers'idle time
            for id in workers:
                workers[id].add_idletime(after-begin_loop)
            
                
        except : #Time out Part
            #print "Master: timeout "
            after = time.time()
            timeout = 1.0

            #We join (old)zombies and we move new ones in the old list
            for id in zombies:
                workers[id].join()
                del workers[id]
            zombies = newzombies
            newzombies = []

            #We add new worker if the queue is > 80% of the worker number
            #print 'Total number of Workers : %d' % len(workers)
            nb_queue = len([elt for elt in verifs.keys() if verifs[elt].get_status() == 'queue'])
            nb_waitforhomerun = len([elt for elt in verifs.keys() if verifs[elt].get_status() == 'waitforhomerun'])

            if not i % 10:
                print 'Stats : Workers:%d Check %d (Queued:%d ReturnWait:%d)' % (len(workers), len(verifs), nb_queue, nb_waitforhomerun)
            
            while nb_queue > 0.8 * len(workers) and len(workers) < 20:
                id = seq_worker.next()
                print "Allocate New worker : ",id
                workers[id]=Worker(id, s, m, mortal=True)
                workers[id].start()
                
            
            #We check for new check
            try:
                new_checks=request_checks.get_checks(do_checks=True, do_actions=True)
            except Pyro.errors.ProtocolError as exp:
                print exp
                #we reinitialise the ccnnexion to pynag
                scheduler_con_init()
                new_checks=[]
            except Exception,x:
                print ''.join(Pyro.util.getPyroTraceback(x))
                sys.exit(0)
            
            #print "********Got %d new checks*******" % len(new_checks)
            for chk in new_checks:
                chk.set_status('queue')
                id = chk.get_id()
                verifs[id] = chk
                msg = Message(id=0, type='Do', data=verifs[id])
                s.put(msg)
            
                
            #We send all finished checks
            manage_return()
            
            
            #We add the time pass on the workers
            for id in workers:
                workers[id].add_idletime(after-begin_loop)
            
            delworkers = []
            #We look for cleaning workers
            for id in workers:
                if workers[id].is_killable():
                    msg=Message(id=0, type='Die')
                    workers[id].send_message(msg)
                    workers[id].set_zombie()
                    delworkers.append(id)
            #Cleaning the workers
            for id in delworkers:
                #del workers[id]
                newzombies.append(id)

