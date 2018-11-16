#!/usr/local/bin/python

'''
TEMPLATE CODE for your reuse
'''

import getpass, argparse, sys, itsi, json
from logger import log

'''
Get user supplied args and setup the itsi.Config object
'''
def setup(argv):

  p = argparse.ArgumentParser(description="Example python script for using itsi.py")

  p.add_argument("boiler_plate")

  # these are optional arguments many have defaults
  p.add_argument("-u", "--user",       help="user with access to run rest calls against ITOA", type=str, default='admin')
  p.add_argument("--pswd",             help="password for named user, no default, should prompt the user if not provided", type=str)
  p.add_argument("-l", "--log_level",  help="log level, 0=debug,1=info,2=warn,3=error", type=int, default=1)
  p.add_argument("-s", "--server",     help="Splunk server", type=str, default='localhost')
  p.add_argument("-p", "--port",       help="port for REST management interface", type=int, default=8089)
  p.add_argument("-r", "--regex",      help="regex to match service titles by, default is .*", type=str, default='.*')
  p.add_argument("-y", "--dryrun",     help="just list the changes and make no commits", action="store_true", default=False)

  # these are positional arguments and must be supplied or it will error
  p.add_argument("new_service_name",     help="will create this service using tpl_demo as a template, fails if that doesn't exist")

  log.db("Who'd have thought log messages could be comments?")
  args = p.parse_args(argv)
  log.setLevel(args.log_level)

  log.info("%s:****@%s:%s, dryrun:%s, regex:%s, positional args: new_service_name:%s\n" % 
    (args.user, args.server, args.port, args.dryrun, args.regex, args.new_service_name))

  if not args.pswd:
    log.db("getting the password because it was not supplied on the command line")
    args.pswd = getpass.getpass('\nEnter Splunk password : ')

  log.db("construct the wrapper for running commands")
  cfg = itsi.Config()
  cfg.setUser(args.user)
  cfg.setHost(args.server)
  cfg.setPort(args.port)
  cfg.setPswd(args.pswd)

  log.db("returning a tuple of args and the config object")
  return (args, cfg)


def doAnUpdate(cfg, args, sampleDescription):
  
  f = itsi.Filter.rex('title', args.new_service_name)
  for svc in cfg.doRead(filter=f, fields='_key,description'):
    log.db("We need the _key to do the update")
    cfg.doUpdate(type='service', 
      template={
        "description": "old: %s, new: %s" % (svc['description'], sampleDescription)
      }, key=svc['_key'])

  log.db("done")

'''
Uses a template service called tpl_demo and copies its KPIs and entity rules
'''
def makeNewService(cfg, args):
  TPL_SVC = 'tpl_demo'
  log.db(" get a list of my template services ")
  templates = {}

  for svc in cfg.doRead(filter=itsi.Filter.rex('title', "^tpl")):
    templates[svc['title']] = svc["_key"]

  log.info("These are my template services, titles mapped to GUIDs:\n" + json.dumps(templates, indent=4))

  if not templates[TPL_SVC]:
    log.fatal("Template Service %s not found."%TPL_SVC, -1)
  
  log.db("This creates a template service using one called tpl_demo as a template, ie it has all its KPIs and entity rules, no service dependencies though")
  tpl = cfg.getTemplate(templates[TPL_SVC])
  cfg.fixKPIs(tpl)
  tpl['title'] = args.new_service_name
  #log.info(json.dumps(tpl, indent=2))
  cfg.doCreate('service', template=tpl)



if __name__ == '__main__':
  log.info("Setting up input arguments")
  args, cfg = setup(sys.argv)

  makeNewService(cfg, args)

  doAnUpdate(cfg, args, "New Description String")