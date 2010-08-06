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


import time
from comment import Comment

class Downtime:
    id = 1

    #Schedules downtime for a specified service. If the "fixed" argument is set
    #to one (1), downtime will start and end at the times specified by the
    #"start" and "end" arguments.
    #Otherwise, downtime will begin between the "start" and "end" times and last
    #for "duration" seconds. The "start" and "end" arguments are specified 
    #in time_t format (seconds since the UNIX epoch). The specified service 
    #downtime can be triggered by another downtime entry if the "trigger_id"
    #is set to the ID of another scheduled downtime entry. 
    #Set the "trigger_id" argument to zero (0) if the downtime for the 
    #specified service should not be triggered by another downtime entry.
    def __init__(self, ref, start_time, end_time, fixed, trigger_id, duration, author, comment):
        self.id = self.__class__.id
        self.__class__.id += 1
        self.ref = ref #pointer to srv or host we are apply
        self.activate_me = [] #The other downtimes i need to activate
        self.entry_time = int(time.time())
        self.fixed = fixed
        self.start_time = start_time
        self.duration = duration
        self.trigger_id = trigger_id
        if self.trigger_id != 0: # triggered plus fixed makes no sense
            self.fixed = False
        self.end_time = end_time
        if fixed:
            self.duration = end_time - start_time
        #This is important for flexible downtimes. Here start_time and
        #end_time mean: in this time interval it is possible to trigger
        #the beginning of the downtime which lasts for duration.
        #Later, when a non-ok event happens, real_end_time will be
        #recalculated from now+duration
        #end_time will be displayed in the web interface, but real_end_time
        #is used internally
        self.real_end_time = end_time
        self.author = author
        self.comment = comment
        self.is_in_effect = False    # fixed: start_time has been reached, flexible: non-ok checkresult
        self.has_been_triggered = False # another downtime has triggered me
        self.can_be_deleted = False
        self.add_automatic_comment()


    def __str__(self):
        if self.is_in_effect == True:
            active = "active"
        else:
            active = "inactive"
        if self.fixed == True:
            type = "fixed"
        else:
            type = "flexible"
        return "%s %s Downtime id=%d %s - %s" % (active, type, self.id, time.ctime(self.start_time), time.ctime(self.end_time))


    def trigger_me(self, other_downtime):
        self.activate_me.append(other_downtime)


    def in_scheduled_downtime(self):
        return self.is_in_effect


    #The referenced host/service object enters now a (or another) scheduled
    #downtime. Write a log message only if it was not already in a downtime
    def enter(self):
        res = []
        self.is_in_effect = True
        if self.fixed == False:
            now = time.time()
            self.real_end_time = now + self.duration
        if self.ref.scheduled_downtime_depth == 0:
            self.ref.raise_enter_downtime_log_entry()
            self.ref.create_notifications('DOWNTIMESTART')
        self.ref.scheduled_downtime_depth += 1
        self.ref.in_scheduled_downtime = True
        for dt in self.activate_me:
            res.extend(dt.enter())
        return res


    #The end of the downtime was reached.
    def exit(self):
        res = []
        if self.is_in_effect == True:
            #This was a fixed or a flexible+triggered downtime
            self.is_in_effect = False
            self.ref.scheduled_downtime_depth -= 1
            if self.ref.scheduled_downtime_depth == 0:
                self.ref.raise_exit_downtime_log_entry()
                self.ref.create_notifications('DOWNTIMEEND')
                self.ref.in_scheduled_downtime = False
        else:
            #This was probably a flexible downtime which was not triggered
            #In this case it silently disappears
            pass
        self.del_automatic_comment()
        self.can_be_deleted = True
        #when a downtime ends and the service was critical 
        #a notification is sent with the next critical check
        #So we should set a flag here which signals consume_result
        #to send a notification
        self.ref.in_scheduled_downtime_during_last_check = True
        return res


    #A scheduled downtime was prematurely cancelled
    def cancel(self):
        res = []
        self.is_in_effect = False
        self.ref.scheduled_downtime_depth -= 1
        if self.ref.scheduled_downtime_depth == 0:
            self.ref.raise_cancel_downtime_log_entry()
            self.ref.in_scheduled_downtime = False
        self.del_automatic_comment()
        self.can_be_deleted = True
        self.ref.in_scheduled_downtime_during_last_check = True
        #Nagios does not notify on cancelled downtimes
        #res.extend(self.ref.create_notifications('DOWNTIMECANCELLED'))
        #Also cancel other downtimes triggered by me
        for dt in self.activate_me:
            res.extend(dt.cancel())
        return res


    #Scheduling a downtime creates a comment automatically
    def add_automatic_comment(self):
        if self.fixed == True:
            text = "This %s has been scheduled for fixed downtime from %s to %s. Notifications for the %s will not be sent out during that time period." % (self.ref.my_type, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time)), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.end_time)), self.ref.my_type)
        else:
            hours, remainder = divmod(self.duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            text = "This %s has been scheduled for flexible downtime starting between %s and %s and lasting for a period of %d hours and %d minutes. Notifications for the %s will not be sent out during that time period." % (self.ref.my_type, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time)), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.end_time)), hours, minutes, self.ref.my_type)
        if self.ref.my_type == 'host':
            comment_type = 1 
        else:
            comment_type = 2
        c = Comment(self.ref, False, "(Nagios Process)", text, comment_type, 2, 0, False, 0)
        self.comment_id = c.id
        self.extra_comment = c
        self.ref.add_comment(c)


    def del_automatic_comment(self):
        self.extra_comment.can_be_deleted = True
        #self.ref.del_comment(self.comment_id)
