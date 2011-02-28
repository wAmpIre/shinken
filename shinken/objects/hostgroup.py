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


from shinken.objects.itemgroup import Itemgroup, Itemgroups

from shinken.property import StringProp

class Hostgroup(Itemgroup):
    id = 1 #0 is always a little bit special... like in database
    my_type = 'hostgroup'

    properties = {
        'id':             StringProp(default=0, fill_brok=['full_status']),
        'hostgroup_name': StringProp(fill_brok=['full_status']),
        'alias':          StringProp(fill_brok=['full_status']),
        'notes':          StringProp(default='', fill_brok=['full_status']),
        'notes_url':      StringProp(default='', fill_brok=['full_status']),
        'action_url':     StringProp(default='', fill_brok=['full_status']),
        'members':        StringProp(default='', fill_brok=['full_status']),
        #Shinken specific
        'unknown_members':StringProp(default=[]),
        'configuration_errors': StringProp(default = []),
    }

    macros = {
        'HOSTGROUPALIAS':     'alias',
        'HOSTGROUPMEMBERS':   'members',
        'HOSTGROUPNOTES':     'notes',
        'HOSTGROUPNOTESURL':  'notes_url',
        'HOSTGROUPACTIONURL': 'action_url'
    }


    def get_name(self):
        return self.hostgroup_name


    def get_hosts(self):
        return getattr(self, 'members', '')


    def get_hostgroup_members(self):
        if self.has('hostgroup_members'):
            return self.hostgroup_members.split(',')
        else:
            return []


    #We fillfull properties with template ones if need
    #Because hostgroup we call may not have it's members
    #we call get_hosts_by_explosion on it
    def get_hosts_by_explosion(self, hostgroups):
        #First we tag the hg so it will not be explode
        #if a son of it already call it
        self.already_explode = True

        #Now the recursiv part
        #rec_tag is set to False avery HG we explode
        #so if True here, it must be a loop in HG
        #calls... not GOOD!
        if self.rec_tag:
            print "Error : we've got a loop in hostgroup definition", self.get_name()
            return self.get_hosts()
        #Ok, not a loop, we tag it and continue
        self.rec_tag = True

        hg_mbrs = self.get_hostgroup_members()
        for hg_mbr in hg_mbrs:
            hg = hostgroups.find_by_name(hg_mbr.strip())
            if hg is not None:
                value = hg.get_hosts_by_explosion(hostgroups)
                if value is not None:
                    self.add_string_member(value)

        return self.get_hosts()



class Hostgroups(Itemgroups):
    name_property = "hostgroup_name" # is used for finding hostgroups
    inner_class = Hostgroup

    def get_members_by_name(self, hgname):
        id = self.find_id_by_name(hgname)
        if id is None:
            return []
        return self.itemgroups[id].get_hosts()


    def linkify(self, hosts=None, realms=None):
        self.linkify_hg_by_hst(hosts)
        self.linkify_hg_by_realms(realms)


    #We just search for each hostgroup the id of the hosts
    #and replace the name by the id
    def linkify_hg_by_hst(self, hosts):
        for hg in self.itemgroups.values():
            mbrs = hg.get_hosts()
            #The new member list, in id
            new_mbrs = []
            for mbr in mbrs:
                if mbr == '*':
                    new_mbrs.extend(hosts)
                else:
                    h = hosts.find_by_name(mbr)
                    if h is not None:
                        new_mbrs.append(h)
                    else:
                        hg.unknown_members.append(mbr)

            #Make members uniq
            new_mbrs = list(set(new_mbrs))

            #We find the id, we remplace the names
            hg.replace_members(new_mbrs)

            #Now register us in our members
            for h in hg.members:
                h.hostgroups.append(hg)
                #and be sure we are uniq in it
                h.hostgroups = list(set(h.hostgroups))


    #More than an explode function, but we need to already
    #have members so... Will be really linkify just after
    #And we explode realm in ours members, but do not overide
    #a host realm value if it's already set
    def linkify_hg_by_realms(self, realms):
        #Now we explode the realm value if we've got one
        #The group realm must not overide a host one (warning?)
        for hg in self:
            if not hasattr(hg, 'realm'): continue

            r = realms.find_by_name(hg.realm.strip())
            if r is not None:
                hg.realm = r
                print "Hostgroup", hg.get_name(), "is in the realm", r.get_name()
            else:
                err = "The hostgroup %s got an unknown realm '%s'" % (hg.get_name(), hg.realm)
                hg.configuration_errors.append(err)
                hg.realm = None
                continue
            
            for h in hg:
                if h is None: continue
                if h.realm is None or h.got_default_realm: #default value not hasattr(h, 'realm'):
                    print "Apply a realm", hg.realm.get_name(), "to host", h.get_name(), "from a hostgroup rule (%s)" % hg.get_name()
                    h.realm = hg.realm
                else:
                    if h.realm != hg.realm:
                        print "Warning : host", h.get_name(), "is not in the same realm than it's hostgroup", hg.get_name()


    #Add a host string to a hostgroup member
    #if the host group do not exist, create it
    def add_member(self, hname, hgname):
        id = self.find_id_by_name(hgname)
        #if the id do not exist, create the hg
        if id is None:
            hg = Hostgroup({'hostgroup_name' : hgname, 'alias' : hgname, 'members' :  hname})
            self.add(hg)
        else:
            self.itemgroups[id].add_string_member(hname)


    #Use to fill members with hostgroup_members
    def explode(self):
        #We do not want a same hg to be explode again and again
        #so we tag it
        for tmp_hg in self.itemgroups.values():
            tmp_hg.already_explode = False
        for hg in self.itemgroups.values():
            if hg.has('hostgroup_members') and not hg.already_explode:
                #get_hosts_by_explosion is a recursive
                #function, so we must tag hg so we do not loop
                for tmp_hg in self.itemgroups.values():
                    tmp_hg.rec_tag = False
                hg.get_hosts_by_explosion(self)

        #We clean the tags
        for tmp_hg in self.itemgroups.values():
            if hasattr(tmp_hg, 'rec_tag'):
                del tmp_hg.rec_tag
            del tmp_hg.already_explode
