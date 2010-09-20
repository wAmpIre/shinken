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


from satellitelink import SatelliteLink, SatelliteLinks
from util import to_int, to_bool, to_split
from item import Items

class ReactionnerLink(SatelliteLink):
    id = 0
    my_type = 'reactionner'
    properties={'reactionner_name' : {'required' : True , 'fill_brok' : ['full_status']},
                'address' : {'required' : True, 'fill_brok' : ['full_status']},
                'port' : {'required':  False, 'default' : '7769', 'pythonize': to_int, 'fill_brok' : ['full_status']},
                'spare' : {'required':  False, 'default' : '0', 'pythonize': to_bool, 'fill_brok' : ['full_status']},
                'manage_sub_realms' : {'required':  False, 'default' : '1', 'pythonize': to_bool, 'fill_brok' : ['full_status']},
                'modules' : {'required' : False, 'default' : '', 'pythonize' : to_split, 'to_send' : True},
                'min_workers' : {'required' : False, 'default' : '1', 'pythonize' : to_int, 'to_send' : True, 'fill_brok' : ['full_status']},
                'max_workers' : {'required' : False, 'default' : '30', 'pythonize' : to_int, 'to_send' : True, 'fill_brok' : ['full_status']},
                'processes_by_worker' : {'required' : False, 'default' : '256', 'pythonize' : to_int, 'to_send' : True, 'fill_brok' : ['full_status']},
                'polling_interval': {'required':  False, 'default' : '1', 'pythonize': to_int, 'to_send' : True, 'fill_brok' : ['full_status']},
                'manage_arbiters' : {'required' : False, 'default' : '0', 'pythonize' : to_int},
                }
 
    running_properties = {'con' : {'default' : None},
                          'alive' : {'default' : False, 'fill_brok' : ['full_status']},                          
                          'broks' : {'default' : []},
                          }
    macros = {}

    def get_name(self):
        return self.reactionner_name


    def register_to_my_realm(self):
        self.realm.reactionners.append(self)



class ReactionnerLinks(SatelliteLinks):#(Items):
    name_property = "name"
    inner_class = ReactionnerLink

