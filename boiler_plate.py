#!/usr/local/bin/python

'''
TEMPLATE CODE for your reuse
'''

import getpass, argparse, sys, itsi, json, logging

'''
Get user supplied args and setup the itsi.Config object
'''
def setup(argv):

  p = argparse.ArgumentParser(description="Example python script for using itsi.py")

  p.add_argument("boiler_plate")

  # these are optional arguments many have defaults
  p.add_argument("-u", "--user",       help="user with access to run rest calls against ITOA", type=str, default='admin')
  p.add_argument("--pswd",             help="password for named user, no default, should prompt the user if not provided", type=str)
  p.add_argument("-l", "--log_level",  help="python logging debug,info,warn,error", type=str, default="warn")
  p.add_argument("-s", "--server",     help="Splunk server", type=str, default='localhost')
  p.add_argument("-p", "--port",       help="port for REST management interface", type=int, default=8089)
  p.add_argument("-r", "--regex",      help="regex to match service titles by, default is .*", type=str, default='.*')
  p.add_argument("-y", "--dryrun",     help="just list the changes and make no commits", action="store_true", default=False)

  # these are positional arguments and must be supplied or it will error
  p.add_argument("new_service_name",     help="will create this service using tpl_demo as a template, fails if that doesn't exist")
  args = p.parse_args(argv)

  itsi.setup_logging(level=args.log_level)

  logger.debug("Who'd have thought log messages could be comments?")


  logging.info("%s:****@%s:%s, dryrun:%s, regex:%s, positional args: new_service_name:%s\n" %
    (args.user, args.server, args.port, args.dryrun, args.regex, args.new_service_name))

  if not args.pswd:
    logging.debug("getting the password because it was not supplied on the command line")
    args.pswd = getpass.getpass('\nEnter Splunk password : ')

  logging.debug("construct the wrapper for running commands")
  cfg = itsi.Config()
  cfg.set_user(args.user)
  cfg.set_host(args.server)
  cfg.set_port(args.port)
  cfg.set_pswd(args.pswd)

  logging.debug("returning a tuple of args and the config object")
  return (args, cfg)


def do_an_update(cfg, args, sampleDescription):
  
  f = itsi.Filter.rex('title', args.new_service_name)
  for svc in cfg.read_config(filter=f, fields='_key,description'):
    logger.debug("We need the _key to do the update")
    cfg.update_config(type='service',
                      template={
        "description": "old: %s, new: %s" % (svc['description'], sampleDescription)
      }, key=svc['_key'])

  logger.debug("done")

'''
Uses a template service called tpl_demo and copies its KPIs and entity rules
'''
def make_new_service(cfg, args):
  TPL_SVC = 'tpl_demo'
  logger.debug(" get a list of my template services ")
  templates = {}

  for svc in cfg.read_config(filter=itsi.Filter.rex('title', "^tpl")):
    templates[svc['title']] = svc["_key"]

  logger.info("These are my template services, titles mapped to GUIDs:\n" + json.dumps(templates, indent=4))

  if not templates[TPL_SVC]:
    logger.fatal("Template Service %s not found."%TPL_SVC, -1)

  logger.debug("This creates a template service using one called tpl_demo as a template, ie it has all its KPIs and entity rules, no service dependencies though")
  tpl = cfg.get_template(templates[TPL_SVC])
  cfg.fix_kpis(tpl)
  tpl['title'] = args.new_service_name
  #log.info(json.dumps(tpl, indent=2))
  cfg.create_config('service', template=tpl)



if __name__ == '__main__':
  logger = logging.getLogger("splunk.bitsi.boiler_plate")
  args, cfg = setup(sys.argv)

  make_new_service(cfg, args)

  do_an_update(cfg, args, "New Description String")