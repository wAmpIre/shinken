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


from itemgroup import Itemgroup, Itemgroups
from brok import Brok
from util import to_bool

#It change from hostgroup Class because there is no members
#propertie, just the realm_members that we rewrite on it.


class Realm(Itemgroup):
    id = 1 #0 is always a little bit special... like in database
    my_type = 'realm'

    properties={'id': {'required': False, 'default': 0, 'status_broker_name' : None},
                'realm_name': {'required': True, 'status_broker_name' : None},
                #'alias': {'required':  True, 'status_broker_name' : None},
                #'notes': {'required': False, 'default':'', 'status_broker_name' : None},
                #'notes_url': {'required': False, 'default':'', 'status_broker_name' : None},
                #'action_url': {'required': False, 'default':'', 'status_broker_name' : None},
                'realm_members' : {'required': False},#No status_broker_name because it put hosts, not host_name
                'higher_realms' : {'required': False},
                'default' : {'required' : False, 'default' : 0, 'pythonize': to_bool}
                }

    macros = {
        'REALMNAME' : 'realm_name',
        'REALMMEMBERS' : 'members',
        }


    def get_name(self):
        return self.realm_name


    def get_realms(self):
        return self.realm_members


    def add_string_member(self, member):
        self.realm_members += ','+member


    def get_realm_members(self):
        if self.has('realm_members'):
            return self.realm_members.split(',')
        else:
            return []


    #Use to make pyton properties
    #TODO : change itemgroup function pythonize?
    def pythonize(self):
        cls = self.__class__
        for prop in cls.properties:
            try:
                tab = cls.properties[prop]
                if 'pythonize' in tab:
                    f = tab['pythonize']
                    old_val = getattr(self, prop)
                    new_val = f(old_val)
                    #print "Changing ", old_val, "by", new_val
                    setattr(self, prop, new_val)
            except AttributeError as exp:
                #print self.get_name(), ' : ', exp
                pass # Will be catch at the is_correct moment


    #We fillfull properties with template ones if need
    #Because hostgroup we call may not have it's members
    #we call get_hosts_by_explosion on it
    def get_realms_by_explosion(self, realms):
        #First we tag the hg so it will not be explode
        #if a son of it already call it
        self.already_explode = True
        
        #Now the recursiv part
        #rec_tag is set to False avery HG we explode
        #so if True here, it must be a loop in HG
        #calls... not GOOD!
        if self.rec_tag:
            print "Error : we've got a loop in realm definition", self.get_name()
            if self.has('members'):
                return self.members
            else:
                return ''
        #Ok, not a loop, we tag it and continue
        self.rec_tag = True

        p_mbrs = self.get_realm_members()
        for p_mbr in p_mbrs:
            p = realms.find_by_name(p_mbr.strip())
            if p is not None:
                value = p.get_realms_by_explosion(realms)
                if value is not None:
                    self.add_string_member(value)

        if self.has('members'):
            return self.members
        else:
            return ''


    def get_schedulers(self):
        r = []
        for s in self.schedulers:
            r.append(s)
        return r


    def get_all_schedulers(self):
        r = []
        for s in self.schedulers:
            r.append(s)
        for p in self.realms:
            tmps = p.get_all_schedulers()
            for s in tmps:
                r.append(s)
        return r



class Realms(Itemgroups):
    name_property = "realm_name" # is used for finding hostgroups
    inner_class = Realm

    def get_members_by_name(self, pname):
        id = self.find_id_by_name(pname)
        if id == None:
            return []
        return self.itemgroups[id].get_realms()


    def linkify(self):
        self.linkify_p_by_p()
        #prepare list of satallites and confs
        for p in self.itemgroups.values():
            p.pollers = []
            p.schedulers = []
            p.reactionners = []
            p.brokers = []
            p.packs = []
            p.confs = {}

    
    #We just search for each realm the others realms
    #and replace the name by the realm
    def linkify_p_by_p(self):
        for p in self.itemgroups.values():
            mbrs = p.get_realm_members()
            #The new member list, in id
            new_mbrs = []
            for mbr in mbrs:
                new_mbr = self.find_by_name(mbr)
                if new_mbr != None:
                    new_mbrs.append(new_mbr)
            #We find the id, we remplace the names
            p.realm_members = new_mbrs
            print "For realm", p.get_name()
            for m in p.realm_members:
                print "Member:", m.get_name()

        #Now put higher realm in sub realms
        #So after they can
        for p in self.itemgroups.values():
            p.higher_realms = []
            
        for p in self.itemgroups.values():
            for sub_p in p.realm_members:
                sub_p.higher_realms.append(p)

#    #Add a host string to a hostgroup member
#    #if the host group do not exist, create it
#    def add_member(self, hname, hgname):
#        id = self.find_id_by_name(hgname)
#        #if the id do not exist, create the hg
#        if id == None:
#            hg = Hostgroup({'hostgroup_name' : hgname, 'alias' : hgname, 'members' :  hname})
#            self.add(hg)
#        else:
#            self.itemgroups[id].add_string_member(hname)


    #Use to fill members with hostgroup_members
    def explode(self):
        #We do not want a same hg to be explode again and again
        #so we tag it
        for tmp_p in self.itemgroups.values():
            tmp_p.already_explode = False
        for p in self.itemgroups.values():
            if p.has('realm_members') and not p.already_explode:
                #get_hosts_by_explosion is a recursive
                #function, so we must tag hg so we do not loop
                for tmp_p in self.itemgroups.values():
                    tmp_p.rec_tag = False
                p.get_realms_by_explosion(self)

        #We clean the tags
        for tmp_p in self.itemgroups.values():
            del tmp_p.rec_tag
            del tmp_p.already_explode