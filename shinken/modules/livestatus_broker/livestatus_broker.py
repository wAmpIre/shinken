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


#This Class is a plugin for the Shinken Broker. It is in charge
#to brok information of the service perfdata into the file
#var/service-perfdata
#So it just manage the service_check_return
#Maybe one day host data will be usefull too
#It will need just a new file, and a new manager :)

import time
import select
import socket
import sys
import cPickle
import sqlite3

from host import Host
from hostgroup import Hostgroup
from service import Service
from servicegroup import Servicegroup
from contact import Contact
from contactgroup import Contactgroup
from timeperiod import Timeperiod
from command import Command
from config import Config
from livestatus import LiveStatus, LOGCLASS_INFO, LOGCLASS_ALERT, LOGCLASS_PROGRAM, LOGCLASS_NOTIFICATION, LOGCLASS_PASSIVECHECK, LOGCLASS_COMMAND, LOGCLASS_STATE, LOGCLASS_INVALID, LOGCLASS_ALL



#Class for the Livestatus Broker
#Get broks and listen to livestatus query language requests
class Livestatus_broker:
    def __init__(self, name, host, port, socket):
        self.host = host
        self.port = port
        self.socket = socket
        self.name = name
        
        #Warning :
        #self.properties will be add by the modulesmanager !!
        

    #Called by Broker so we can do init stuff
    #TODO : add conf param to get pass with init
    #Conf from arbiter!
    def init(self):
        print "I am init"
        self.q = self.properties['to_queue']
    
        #Our datas
        self.configs = {}
        self.hosts = {}
        self.services = {}
        self.contacts = {}
        self.hostgroups = {}
        self.servicegroups = {}
        self.contactgroups = {}
        self.timeperiods = {}
        self.commands = {}

        self.hostname_lookup_table = {}
        self.servicename_lookup_table = {}

        self.prepare_log_db()
        self.livestatus = LiveStatus(self.configs, self.hosts, self.services, self.contacts, self.hostgroups, self.servicegroups, self.contactgroups, self.timeperiods, self.commands, self.dbconn)

        self.number_of_objects = 0
    

    def is_external(self):
        return True


    def get_name(self):
        return self.name


    #Get a brok, parse it, and put in in database
    #We call functions like manage_ TYPEOFBROK _brok that return us queries
    def manage_brok(self, b):
        type = b.type
        manager = 'manage_'+type+'_brok'
        #print "------------------------------------------- i receive", manager
        if hasattr(self, manager):
            #print "------------------------------------------- i manage", manager
            #print b
            f = getattr(self, manager)
            f(b)


    def manage_program_status_brok(self, b):
        data = b.data
        c_id = data['instance_id']
        #print "Creating config:", c_id, data
        c = Config()
        for prop in data:
            setattr(c, prop, data[prop])
        #print "CFG:", c
        self.configs[c_id] = c


    def manage_initial_host_status_brok(self, b):
        data = b.data
        h_id = data['id']
        #print "Creating host:", h_id, data
        h = Host({})
        for prop in data:
            setattr(h, prop, data[prop])
        h.check_period = self.get_timeperiod(h.check_period)
        h.notification_period = self.get_timeperiod(h.notification_period)
        h.contacts = self.get_contacts(h.contacts)
        #Escalations is not use for status_dat
        del h.escalations
                
        h.service_ids = []
        h.services = []
        self.hosts[h_id] = h
        self.hostname_lookup_table[h.host_name] = h_id
        self.number_of_objects += 1


    def manage_initial_hostgroup_status_brok(self, b):
        data = b.data
        hg_id = data['id']
        members = data['members']
        del data['members']
        #print "Creating hostgroup:", hg_id, data
        hg = Hostgroup()
        for prop in data:
            setattr(hg, prop, data[prop])
        setattr(hg, 'members', [])
        for (h_id, h_name) in members:
            if h_id in self.hosts:
                hg.members.append(self.hosts[h_id])
        #print "HG:", hg
        self.hostgroups[hg_id] = hg
        self.number_of_objects += 1


    def manage_initial_service_status_brok(self, b):
        data = b.data
        s_id = data['id']
        #print "Creating Service:", s_id, data
        s = Service({})
        self.update_element(s, data)

        s.check_period = self.get_timeperiod(s.check_period)
        s.notification_period = self.get_timeperiod(s.notification_period)

        s.contacts = self.get_contacts(s.contacts)

        del s.escalations

        h = self.find_host(data['host_name'])
        if h != None:
            # Reconstruct the connection between hosts and services
            h.service_ids.append(s_id)
            h.services.append(s)
            # There is already a s.host_name, but a reference to the h object can be useful too
            s.host = h
        self.services[s_id] = s
        self.servicename_lookup_table[s.host_name + s.service_description] = s_id
        self.number_of_objects += 1



    def manage_initial_servicegroup_status_brok(self, b):
        data = b.data
        sg_id = data['id']
        members = data['members']
        del data['members']
        #print "Creating servicegroup:", sg_id, data
        sg = Servicegroup()
        for prop in data:
            setattr(sg, prop, data[prop])
        setattr(sg, 'members', [])
        for (s_id, s_name) in members:
            if s_id in self.services:
                sg.members.append(self.services[s_id])
        #print "SG:", sg
        self.servicegroups[sg_id] = sg
        self.number_of_objects += 1


    def manage_initial_contact_status_brok(self, b):
        data = b.data
        c_id = data['id']
        #print "Creating Contact:", c_id, data
        c = Contact({})
        self.update_element(c, data)
        #print "C:", c
        self.contacts[c_id] = c
        self.number_of_objects += 1


    def manage_initial_contactgroup_status_brok(self, b):
        data = b.data
        cg_id = data['id']
        members = data['members']
        del data['members']
        print "Creating contactgroup:", cg_id, data
        cg = Contactgroup()
        for prop in data:
            setattr(cg, prop, data[prop])
        setattr(cg, 'members', [])
        for (c_id, c_name) in members:
            if c_id in self.contacts:
                cg.members.append(self.contacts[c_id])
        print "CG:", cg
        self.contactgroups[cg_id] = cg
        self.number_of_objects += 1


    def manage_initial_timeperiod_status_brok(self, b):
        data = b.data
        tp_id = data['id']
        print "Creating Timeperiod:", tp_id, data
        tp = Timeperiod({})
        self.update_element(tp, data)
        print "TP:", tp
        self.timeperiods[tp_id] = tp
        self.number_of_objects += 1


    def manage_initial_command_status_brok(self, b):
        data = b.data
        c_id = data['id']
        print "Creating Command:", c_id, data
        c = Command({})
        self.update_element(c, data)
        print "CMD:", c
        self.commands[c_id] = c
        self.number_of_objects += 1


    #A service check have just arrived, we UPDATE data info with this
    def manage_service_check_result_brok(self, b):
        data = b.data
        s = self.find_service(data['host_name'], data['service_description'])
        if s != None:
            self.update_element(s, data)
            #print "S:", s


    #A service check update have just arrived, we UPDATE data info with this
    def manage_service_next_schedule_brok(self, b):
        self.manage_service_check_result_brok(b)


    #In fact, an update of a service is like a check return
    def manage_update_service_status_brok(self, b):
        self.manage_service_check_result_brok(b)
        data = b.data
        #In the status, we've got duplicated item, we must relink thems
        s = self.find_service(data['host_name'], data['service_description'])
        s.check_period = self.get_timeperiod(s.check_period)
        s.notification_period = self.get_timeperiod(s.notification_period)
        s.contacts = self.get_contacts(s.contacts)
        del s.escalations


    def manage_host_check_result_brok(self, b):
        data = b.data
        h = self.find_host(data['host_name'])
        if h != None:
            self.update_element(h, data)
            #print "H:", h


    # this brok should arrive within a second after the host_check_result_brok
    def manage_host_next_schedule_brok(self, b):
        self.manage_host_check_result_brok(b)


    #In fact, an update of a host is like a check return
    def manage_update_host_status_brok(self, b):
        self.manage_host_check_result_brok(b)
        data = b.data
        #In the status, we've got duplicated item, we must relink thems
        h = self.find_host(data['host_name'])
        h.check_period = self.get_timeperiod(h.check_period)
        h.notification_period = self.get_timeperiod(h.notification_period)
        h.contacts = self.get_contacts(h.contacts)
        #Escalations is not use for status_dat
        del h.escalations


    #A log brok will be written into a database
    def manage_log_brok(self, b):
        data = b.data
        line = data['log'].encode('UTF-8').rstrip()
        # split line and make sql insert
        print "LOG--->", line
        # [1278280765] SERVICE ALERT: test_host_0
        # split leerzeichen
        if line[0] != '[' and line[11] != ']':
            pass
            print "INVALID"
            # invalid
        else:
            service_states = { 'OK' : 0, 'WARNING' : 1, 'CRITICAL' : 2, 'UNKNOWN' : 3, 'RECOVERY' : 0 }
            host_states = { 'UP' : 0, 'DOWN' : 1, 'UNREACHABLE' : 2, 'RECOVERY' : 0 }

            # 'attempt', 'class', 'command_name', 'comment', 'contact_name', 'host_name', 'lineno', 'message',
            # 'options', 'plugin_output', 'service_description', 'state', 'state_type', 'time', 'type',
            # 0:info, 1:state, 2:program, 3:notification, 4:passive, 5:command

            # lineno, message?, plugin_output?
            logclass = LOGCLASS_INVALID
            attempt, command_name, comment, contact_name, host_name, message, options, plugin_output, service_description, state, state_type = [None] * 11
            time= line[1:11]
            print "i start with a timestamp", time
            first_type_pos = line.find(' ') + 1
            last_type_pos = line.find(':')
            first_detail_pos = last_type_pos + 2
            type = line[first_type_pos:last_type_pos]
            options = line[first_detail_pos:]
            message = line
            if type == 'CURRENT SERVICE STATE':
                logclass = LOGCLASS_STATE
                host_name, service_description, state, state_type, attempt, plugin_output = options.split(';')
            elif type == 'INITIAL SERVICE STATE':
                logclass = LOGCLASS_STATE
                host_name, service_description, state, state_type, attempt, plugin_output = options.split(';')
            elif type == 'SERVICE ALERT':
                # SERVICE ALERT: srv-40;Service-9;CRITICAL;HARD;1;[Errno 2] No such file or directory
                logclass = LOGCLASS_ALERT
                host_name, service_description, state, state_type, attempt, plugin_output = options.split(';')
                state = service_states[state]
            elif type == 'SERVICE DOWNTIME ALERT':
                logclass = LOGCLASS_ALERT
                host_name, service_description, state_type, comment = options.split(';')
            elif type == 'SERVICE FLAPPING ALERT':
                logclass = LOGCLASS_ALERT
                host_name, service_description, state_type, comment = options.split(';')

            elif type == 'CURRENT HOST STATE':
                logclass = LOGCLASS_STATE
                host_name, state, state_type, attempt, plugin_output = options.split(';')
            elif type == 'INITIAL HOST STATE':
                logclass = LOGCLASS_STATE
                host_name, state, state_type, attempt, plugin_output = options.split(';')
            elif type == 'HOST ALERT':
                logclass = LOGCLASS_ALERT
                host_name, state, state_type, attempt, plugin_output = options.split(';')
                state = host_states[state]
            elif type == 'HOST DOWNTIME ALERT':
                logclass = LOGCLASS_ALERT
                host_name, state_type, comment = options.split(';')
            elif type == 'HOST FLAPPING ALERT':
                logclass = LOGCLASS_ALERT
                host_name, state_type, comment = options.split(';')

            elif type == 'SERVICE NOTIFICATION':
                # tust_cuntuct;test_host_0;test_ok_0;CRITICAL;notify-service;i am CRITICAL  <-- normal
                # SERVICE NOTIFICATION: test_contact;test_host_0;test_ok_0;DOWNTIMESTART (OK);notify-service;OK
                logclass = LOGCLASS_NOTIFICATION
                contact_name, host_name, service_description, state_type, command_name, check_plugin_output = options.split(';')
                if '(' in state_type: # downtime/flapping/etc-notifications take the type UNKNOWN
                    state_type = 'UNKNOWN'
                state = service_states[state_type]
            elif type == 'HOST NOTIFICATION':
                # tust_cuntuct;test_host_0;DOWN;notify-host;i am DOWN
                logclass = LOGCLASS_NOTIFICATION
                contact_name, host_name, state_type, command_name, check_plugin_output = options.split(';')
                if '(' in state_type:
                    state_type = 'UNKNOWN'
                state = host_states[state_type]

            elif type == 'PASSIVE SERVICE CHECK':
                logclass = LOGCLASS_PASSIVECHECK
                host_name, service_description, state, check_plugin_output = options.split(';')
            elif type == 'PASSIVE HOST CHECK':
                logclass = LOGCLASS_PASSIVECHECK
                host_name, state, check_plugin_output = options.split(';')

            elif type == 'SERVICE EVENT HANDLER':
                # SERVICE EVENT HANDLER: test_host_0;test_ok_0;CRITICAL;SOFT;1;eventhandler
                host_name, service_description, state, state_type, attempt, command_name = options.split(';')
                state = service_states[state]
            elif type == 'HOST EVENT HANDLER':
                host_name, state, state_type, attempt, command_name = options.split(';')
                state = host_states[state]

            elif type == 'EXTERNAL COMMAND':
                logclass = LOGCLASS_COMMAND
            elif type.startswith('starting...') or \
                 type.startswith('shutting down...') or \
                 type.startswith('Bailing out') or \
                 type.startswith('active mode...') or \
                 type.startswith('standby mode...'):
                logclass = LOGCLASS_PROGRAM
            else:
                print "does not match"

            lineno = 0

            try:
                values = (attempt, logclass, command_name, comment, contact_name, host_name, lineno, message, options, plugin_output, service_description, state, state_type, time, type)
            except:
                print "Unexpected error:", sys.exc_info()[0]
            #print "LOG:", logclass, type, host_name, service_description, state, state_type, attempt, plugin_output, contact_name, comment, command_name
            print "LOG:", values
            try:
                if logclass != LOGCLASS_INVALID:
                    self.dbcursor.execute('INSERT INTO LOGS VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', values)
                    self.dbconn.commit()
            except sqlite3.Error, e:
                print "An error occurred:", e.args[0]
                print "DATABASE ERROR!!!!!!!!!!!!!!!!!"


    #The contacts must not be duplicated
    def get_contacts(self, cs):
        r = []
        for c in cs:
            if c != None:
                find_c = self.find_contact(c.get_name())
                if find_c != None:
                    r.append(find_c)
                else:
                    print "Error : search for a contact %s that do not exists!" % c.get_name()
        return r


    #The timeperiods must not be duplicated
    def get_timeperiod(self, t):
        if t != None:
            find_t = self.find_timeperiod(t.get_name())
            if find_t != None:
                return find_t
            else:
                print "Error : search for a timeperiod %s that do not exists!" % t.get_name()
        else:
            return None


    def find_host(self, host_name):
        if host_name in self.hostname_lookup_table:
            return self.hosts[self.hostname_lookup_table[host_name]]
        for h in self.hosts.values():
            if h.host_name == host_name:
                return h
        return None


    def find_service(self, host_name, service_description):
        if host_name + service_description in self.servicename_lookup_table:
            return self.services[self.servicename_lookup_table[host_name + service_description]]
        for s in self.services.values():
            if s.host_name == host_name and s.service_description == service_description:
                return s
        return None


    def find_timeperiod(self, timeperiod_name):
        for t in self.timeperiods.values():
            if t.timeperiod_name == timeperiod_name:
                return t
        return None


    def find_contact(self, contact_name):
        for c in self.contacts.values():
            if c.contact_name == contact_name:
                return c
        return None

        
    def update_element(self, e, data):
        #print "........%s........" % type(e)
        for prop in data:
            #if hasattr(e, prop):
            #    print "%-20s\t%s\t->\t%s" % (prop, getattr(e, prop), data[prop])
            #else:
            #    print "%-20s\t%s\t->\t%s" % (prop, "-", data[prop])
            setattr(e, prop, data[prop])


    def prepare_log_db(self):
        # create db file and tables if not existing
        self.dbconn = sqlite3.connect('/tmp/livelogs.db')
        self.dbcursor = self.dbconn.cursor()
        # 'attempt', 'class', 'command_name', 'comment', 'contact_name', 'host_name', 'lineno', 'message',
        # 'options', 'plugin_output', 'service_description', 'state', 'state_type', 'time', 'type',
        cmd = "CREATE TABLE IF NOT EXISTS logs(attempt INT, class INT, command_name VARCHAR(64), comment VARCHAR(256), contact_name VARCHAR(64), host_name VARCHAR(64), lineno INT, message VARCHAR(512), options INT, plugin_output VARCHAR(256), service_description VARCHAR(64), state INT, state_type VARCHAR(10), time INT, type VARCHAR(64))"
        self.dbcursor.execute(cmd)
        self.dbconn.commit()
        self.dbconn.row_factory = sqlite3.Row


    def main(self):
        last_number_of_objects = 0
        backlog = 5
        size = 8192
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setblocking(0)
        server.bind((self.host, self.port))
        server.listen(backlog)
        input = [server]
        databuffer = {}
        # todo. open self.socket and add it to input

        while True:
            try:
                b = self.q.get(True, .01)  # do not block indefinitely
                self.manage_brok(b)
            except Exception:
                pass
            inputready,outputready,exceptready = select.select(input,[],[], 0)

            for s in inputready:
                if s == server:
                    # handle the server socket
                    client, address = server.accept()
                    input.append(client)
                else:
                    # handle all other sockets
                    data = s.recv(size)
                    if s in databuffer:
                        databuffer[s] += data
                    else:
                        databuffer[s] = data
                    if not data or databuffer[s].endswith('\n\n'):
                        # end-of-transmission or an empty line was received
                        response = self.livestatus.handle_request(databuffer[s].rstrip())
                        del databuffer[s]
                        s.send(response)
                        try:
                            s.shutdown(2)
                        except Exception , exp:
                            print exp
                        s.close()
                        input.remove(s)

            if self.number_of_objects > last_number_of_objects:
                # Still in the initialization phase
                # Maybe we should wait until there are no more initial broks
                # before we open the socket
                pass