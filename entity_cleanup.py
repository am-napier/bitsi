#!/usr/bin/python

"""

"""

import argparse
import getpass
import itsi
import logging
import sys
import time

"""
Update entities based on groups of things
"""


def setup(argv):
    # type: (object) -> object

    p = argparse.ArgumentParser(description="Example python script for using itsi.py")

    p.add_argument("create_threshold_templates")

    # these are optional arguments many have defaults
    p.add_argument("-u", "--user", help="user with access to run rest calls against ITOA", type=str, default='admin')
    p.add_argument("--pswd", help="password for named user, no default, should prompt the user if not provided",
                   type=str)
    p.add_argument("-l", "--log_level", help="python logging debug,info,warn,error", type=str, default="warn")
    p.add_argument("-s", "--server", help="Splunk server", type=str, default='localhost')
    p.add_argument("-p", "--port", help="port for REST management interface", type=int, default=8089)

    p.add_argument("-y", "--dryrun", help="just list the changes and make no commits", action="store_true",
                   default=False)


    args2 = p.parse_args(argv)
    itsi.setup_logging(level=args2.log_level)

    if not args2.pswd:
        # getting the password because it was not supplied on the command line
        args2.pswd = getpass.getpass('\nEnter Splunk password : ')

    # construct the wrapper for running commands
    cfg = itsi.Config(user=args2.user, host=args2.server, port=args2.port, pswd=args2.pswd)

    # returning a tuple of args and the config object
    return (args2, cfg)

ENTITIES = {}



def netapp_vserver(cfg):
    f = itsi.Filter.rex("description", "This is an SVM within a storage array")
    arr = cfg.read_config('entity', fields="title,_key,identifier,informational", filter=f)

    moveAliasFieldsToInfo(cfg, "host", "host", arr)
    moveAliasFieldsToInfo(cfg, "vserver-name", "vserver-name", arr)

def moveAliasToInfo(cfg, field):
    f = itsi.Filter.rex("identifier.fields", "^"+field+"$")
    entities = cfg.read_config('entity', fields="title,_key,identifier,informational", filter=f)
    moveAliasFieldsToInfo(cfg, field, field, entities)


def get_alias(entity, alias):
    # get an alias value from an entity object
    fields = entity['identifier']['fields']
    values = entity['identifier']['values']

    if alias in fields:
        if fields.index(alias) < len(values):
            return values[fields.index(alias)]
    else:
        return None


'''
get all info vendor_product=Linux, itsi_role=operating_system_host and dv_name doesn't exist
for each find the alias host and search for dv_name with the same value
merge the two entities and delete the other 
'''
def fix_linux_os(cfg):
    os_hosts_filter = '{ "informational.fields": {"$regex":"^vendor_product$"}, "informational.values": {"$regex":"^operating_system_host"} }'
    gsn_host_filter = '{ "identifier.fields": {"$regex":"^dv_name$"}, "informational.values": {"$regex":"^operating_system_host"} }'

    os_hosts = cfg.read_config('entity', fields="title,_key,identifier,informational", filter=os_hosts_filter)
    gsn_hosts = cfg.read_config('entity', fields="title,_key,identifier,informational", filter=gsn_host_filter)

    logger.info("%d %d" % (len(os_hosts), len(gsn_hosts)))

    hosts_to_merge = []
    hosts_to_delete = []
    for os_entity in os_hosts:
        host = get_alias(os_entity, "host")
        if host == None:
            logger.info("no host for %s, skipped" % (os_entity['title']))
            continue
        for gsn_entity in gsn_hosts:
            dv_name = get_alias(gsn_entity, "dv_name")
            if dv_name == None:
                logger.info("no dv_name for %s, skipped" % (gsn_entity['title']))
                continue
            if dv_name == host:
                # adding a tuple (os, gsn)
                hosts_to_merge.append((os_entity, gsn_entity))
                logger.info("merging on %s" % (dv_name))

    logger.info("found %d entities to merge" % (len(hosts_to_merge)))


'''
Move disk_name to an info field
'''
def moveAliasFieldsToInfo(cfg, field, field_to, entities):

    n = 0
    logger.info("start moving %d fields: %s from alias to info" % (len(entities), field))
    start = time.time()
    T_INC=10
    t = start+T_INC
    for e in entities:
        # get the disk name and move it to the info fields at the start of the list
        key = e['_key']
        try:
            e = ENTITIES[key]
        except KeyError:
            ENTITIES[key] = e

        alias_names = e['identifier']['fields']
        alias_values = e['identifier']['values']
        info_names = e['informational']['fields']
        info_values = e['informational']['values']


        try:
            idx = alias_names.index(field)
            info_names = info_names.insert(0, field_to)
            info_values = info_values.insert(0, alias_values[idx])


            del alias_names[idx]
            del alias_values[idx]

            #log.info("updating %s"%(e['title']))
            n = n+1
            if time.time() > t:
                logger.info("updated %d items in %0.1f" % (n, (time.time()-start)))
                t = time.time()+T_INC

        except:
            logger.info("Skipped %s probably no key %s in %s" % (e['title'],  field, str(alias_names)))
            continue

    logger.info("finished moving %d fields: '%s' from alias to info in %0.1f secs" % (n, field, (time.time()-start)))


if __name__ == '__main__':
    logger = logging.getLogger("splunk.bitsi.create_threshold_templates")

    args, cfg = setup(sys.argv)
    os_hosts_filter = '{ "informational.fields": {"$regex":"^vendor_product$"}, "informational.values": {"$regex":"^operating_system_host"} }'
    os_hosts = cfg.read_config('entity', fields="title,_key,identifier,informational", filter=os_hosts_filter)


    alias_to_infos="pool_name,disk_name,fabric_name,fabric_id,dv_u_ilo_ip_address,qtree,vserver,volume_name,site,site2"

    for alias in alias_to_infos.split(","):
        moveAliasToInfo(cfg, alias)


    fix_linux_os(cfg);

    # do the updates
    start = time.time()
    T_INC=10
    t = start+T_INC
    n=0

    data = []
    for key in ENTITIES:
        data.append(ENTITIES[key])
        n=n+1
        UPDATE_SZ=250
        if len(data) == UPDATE_SZ:
            cfg.bulk_update_config('entity', data)
            #cfg.update_config('entity', ENTITIES[key], key)
            logger.info("updated %d of %d items in %0.1f - %d - %s" % (n, len(ENTITIES), (time.time()-start), len(data), ENTITIES[key]['title']))
            t = time.time()+T_INC
            data = []
    if len(data) > 0:
        cfg.bulk_update_config('entity', data)
        logger.info("Last update %d of %d items in %0.1f - %d" % (n, len(ENTITIES), (time.time() - start), len(data)))


