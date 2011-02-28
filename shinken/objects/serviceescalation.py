#!/usr/bin/env python
#Copyright (C) 2009-2010 :
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
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

from shinken.objects.item import Item, Items
from shinken.objects.escalation import Escalation

from shinken.property import IntegerProp, StringProp, ListProp

class Serviceescalation(Item):
    id = 1 #0 is always special in database, so we do not take risk here
    my_type = 'serviceescalation'

    properties = {
        'host_name':             StringProp (),
        'hostgroup_name':        StringProp (),
        'service_description':   StringProp (),
        'first_notification':    IntegerProp(),
        'last_notification':     IntegerProp(),
        'notification_interval': IntegerProp(),
        'escalation_period':     StringProp (default=''),
        'escalation_options':    ListProp   (default='d,u,r,w,c'),
        'contacts':              StringProp (),
        'contact_groups':        StringProp (),
    }

    running_properties = {}

    macros = {}


    #For debugging purpose only (nice name)
    def get_name(self):
        return ''


class Serviceescalations(Items):
    name_property = ""
    inner_class = Serviceescalation


    #We look for contacts property in contacts and
    def explode(self, escalations):
        #Now we explode all escalations (host_name, service_description) to escalations
        for es in self:
            properties = es.__class__.properties

            creation_dict = {'escalation_name' : 'Generated-Serviceescalation-%d' % es.id}
            for prop in properties:
                if hasattr(es, prop):
                    creation_dict[prop] = getattr(es, prop)
            #print "Creation an escalation with :", creation_dict
            s = Escalation(creation_dict)
            escalations.add_escalation(s)
