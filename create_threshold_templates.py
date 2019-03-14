#!/usr/bin/python

"""
Reads a CSV file that lists out various options to make threshold template configurations and uploads these to your ITSI via REST

The process does the following:
1. Reads a policy via REST by name (--default_template) to use as a template and deletes all the policy nodes.  Terminates if the policy can't be found.
2. Reads a CSV of templates to create.  Terminates if CSV is bad
3. For each new policy from CSV
        i. copies the default policy and adds a new time based policy for each line
        ii. loads that as a new object into the instance via REST
4. Every template will get a simple default policy added that is static info only so it shows gaps as blue bars

To use this process I expect you will create the CSV, run the script and upload the policies, check they are good and if they don't work delete them and rerun.
Only once they are good will they be used on services because once they hit the services you can only update via the UI not the CSV.
Proper use of service templates though will help this process.

CSV input file must be UTF-8 without BOM or the reader freaks out, fix in your fav editor, saving as excel adds the BOM.

Example: assuming python is installed run this

./create_threshold_template.py --server splunk_server --log_level 0 -u admin [--pswd changeme] ./test_daily.csv

if pswd is not passed it will be prompted for and obviously user needs permissions to read and create templates via REST.

Fields in the CSV are as follows:

    template:   the name of the template to be created in the UI.  Use multiple rows with identical values to get multiple patterns, based on days
    disabled:   set to 1 to stop that row running during the load
    days:       day range, eitehr a single integer or a range 'a-b' for a set of days.  If you want 7 different days use 7 rows and vary just the day column.  For week days and weekends use two rows with 0-4 and 5-6
    start:      ignore - supports another mode that allows time blocks within a day to be specified but not needed
    end:        ignore
    type:       one of range,quantile,stdev
    AGG_BASE:   set the aggregate policy base severity*
    AT{n*}:     sets the severity* for this level of this AGGREGATE policy
    AV{n*}:     sets the dynamicParam value of this AGGREGATE policy
    ENT_BASE:   set the entity policy base severity* to one of info,normal,low,medium.high or critical
    ET{n*}:     sets the severity* for this level of this ENTITY policy
    EV{n*}:     sets the dynamicParam value of this ENTITY policy

where
* severity is one of info,normal,low,medium.high or critical
* n is an integer increasing from 1 that orders the aggregate or entity based poilicies, for example
AT1=low, AV1=-3 (assuming type is stdev) would set the first aggregate policy to low at -1 stdev
ET2=high, ET2=90 (assuming ET1 was set) will set the second level entity policy to high at or above 95

If ATn or ETn is specified it must have a corresponding AVn or EVn or a key error will be raised.

This library depends upon the log and itsi modules bundled here, gthub todo soooner or later
You'll also need requests module available in your python.  Note splunk has this so should be good to go with

    $SPLUNK_HOME/bin/splunk cmd python create_threshold_template.py ....

"""

import getpass, argparse, sys, itsi, json, csv, copy, logging

"""
Get user supplied args and setup the itsi.Config object
"""


def setup(argv):
    # type: (object) -> object

    p = argparse.ArgumentParser(description="Example python script for using itsi.py")

    p.add_argument("create_threshold_templates")

    # these are optional arguments many have defaults
    p.add_argument("-u", "--user", help="user with access to run rest calls against ITOA", type=str, default='admin')
    p.add_argument("--pswd", help="password for named user, no default, should prompt the user if not provided",
                   type=str)
    p.add_argument("-l", "--log_level", help="log level, 0=debug,1=info,2=warn,3=error", type=int, default=1)
    p.add_argument("-s", "--server", help="Splunk server", type=str, default='localhost')
    p.add_argument("-p", "--port", help="port for REST management interface", type=int, default=8089)
    p.add_argument("-d", "--default_template",
                   help="id of the template to clone, defaults to '1-hour blocks every day (adaptive/quantile)'",
                   type=str, default="kpi_threshold_template_3_quantile")
    p.add_argument("-t", "--type",
                   help="type of update, regular or custom, regular takes one line per period and replicates over days specified, custom just builds one period per line",
                   type=str, default="regular")
    p.add_argument("-y", "--dryrun", help="just list the changes and make no commits", action="store_true",
                   default=False)

    # these are positional arguments and must be supplied or it will error
    p.add_argument("infile", help="the name of the input file")

    args = p.parse_args(argv)
    itsi.setup_logging(level=args.log_level)

    logger.debug("Reading from inputs %s" % args.infile)

    if not args.pswd:
        # getting the password because it was not supplied on the command line
        args.pswd = getpass.getpass('\nEnter Splunk password : ')

    # construct the wrapper for running commands
    cfg = itsi.Config(user=args.user, host=args.server, port=args.port, pswd=args.pswd)

    # returning a tuple of args and the config object
    return (args, cfg)


sevMap = {
    "info": {"value": 1, "color": "#AED3E5", "colorlight": "#E3F0F6"},
    "normal": {"value": 2, "color": "#DCEFD7", "colorlight": "#99D18B"},
    "low": {"value": 3, "color": "#FFE98C", "colorlight": "#FFF4C5"},
    "medium": {"value": 4, "color": "#FCB64E", "colorlight": "#FEE6C1"},
    "high": {"value": 5, "color": "#F26A35", "colorlight": "#FBCBB9"},
    "critical": {"value": 6, "color": "#B50101", "colorlight": "#E5A6A6"}
}


def get_thresholds(cfg, entity=False):
    type = 'E' if entity else 'A'
    arr = []
    n = 1
    while True:
        try:
            if cfg[type + "T" + str(n)] in sevMap:
                arr.append((n, cfg[type + "T" + str(n)], cfg[type + "V" + str(n)]))
            n = n + 1
        except KeyError:
            break

    baseSev = cfg['ENT_BASE'] if entity else cfg['AGG_BASE']
    res = {
        "isMaxStatic": False,
        "metricField": "count",
        "renderBoundaryMin": 0,
        "gaugeMax": 1,
        "gaugeMin": 0,
        "isMinStatic": True,
        "renderBoundaryMax": 100,
        "baseSeverityLabel": baseSev,
        "baseSeverityColor": sevMap[baseSev]['color'],
        "baseSeverityValue": sevMap[baseSev]['value'],
        "baseSeverityColorLight": sevMap[baseSev]['colorlight'],
        'thresholdLevels': []
    }
    for n, thr, val in arr:
        res['thresholdLevels'].append({
            "dynamicParam": 0 if entity else val,
            "thresholdValue": val if entity else n,
            "severityValue": sevMap[thr]['value'],
            "severityLabel": thr,
            "severityColor": sevMap[thr]['color'],
            "severityColorLight": sevMap[thr]['colorlight']
        })
    return res


def get_default_policy():
    # have to add a single threshold group to the aggregate or it won't apply when its loaded
    return {
        "entity_thresholds": get_thresholds({'ENT_BASE': 'info', 'AGG_BASE': 'info'}),
        "time_blocks": [],
        "aggregate_thresholds": get_thresholds({'ENT_BASE': 'info', 'AGG_BASE': 'info', 'AT1': 'info', 'AV1': '0'}, entity=False),
        "title": "Default",
        "policy_type": "quantile"
    }


def updatePolicies(policies, policy_type):
    """
    Make the policy title value.
    Pattern will be Start_Day[-End_Day] Start-End (method)
    eg for Days 1-5 Start=01:00 End=01:30 type=range the title will be
    M-F 01:00-01:30 (range)
    eg for Days 0,2,3,4 Start=01:00 End=03:45 type=stdev the title will be
    M,W,Th,F 01:00-01:30 (stdev)
    """
    days = str(r['days']).replace("0", "M").replace("1", "Tu").replace("2", "W").replace("3", "Th"). \
        replace("4", "F").replace("5", "Sa").replace("6", "Su")

    if policy_type == "regular":
        for i in range(0, 24):
            start = "%02d:00" % i
            end = "%02d:00" % (i + 1)
            title = "%s %s-%s (%s)" % (days, start, end, r['type'])

            policies[title] = {
                'title': title,
                'policy_type': r['type'],
                'time_blocks': [["0 %d * * %s" % (i, str(r['days'])), 60]],
                'entity_thresholds': get_thresholds(r, entity=True),
                'aggregate_thresholds': get_thresholds(r)
            }
    elif policy_type == "custom":
        start = r['start']
        end = r['end']
        # end times of 00:00 or 0:00 are reallly 24:00
        if end == "0:00" or end == "00:00":
            end = "24:00"

        title = "%s %s-%s (%s)" % (days, start, end, r['type'])

        start_toks = start.split(":")
        end_toks = end.split(":")
        try:
            cron = "%d %d * * %s" % (int(start_toks[1]), int(start_toks[0]), str(r['days']))
        except IndexError:
            logger.info("Index Error for break point")
            sys.exit(-1)
        duration = (int(end_toks[0]) * 60 + int(end_toks[1])) - (int(start_toks[0]) * 60 + int(start_toks[1]))
        policies[title] = {
            'title': title,
            'policy_type': r['type'],
            'time_blocks': [[cron, duration]],
            'entity_thresholds': get_thresholds(r, entity=True),
            'aggregate_thresholds': get_thresholds(r)
        }
    else:
        logger.error("Unknown type passed")


if __name__ == '__main__':
    logger = logging.getLogger("splunk.bitsi.create_threshold_templates")
    args, cfg = setup(sys.argv)

    tpl = cfg.read_config('kpi_threshold_template', key=args.default_template)
    if tpl == None:
        logger.error("KPI Template not found: %s" % args.default_template)

    # don't want the _key on the template
    del tpl['_key']
    # reset this so user can change it
    tpl['_immutable'] = 0

    tpl['identifying_name'] = "blank"
    tpl['title'] = "blank blank"
    tpl['acl']['owner'] = args.user

    templates = {}
    # read the file, for each line
    with open(args.infile) as fp:
        reader = csv.DictReader(fp)
        headers = reader.fieldnames
        for r in reader:
            if r['disabled'] == "1":
                continue

            try:
                template = templates[r['template']]
            except KeyError:
                if r['template'] == "":
                    logger.info("can't process row (%s)" % str(r))
                    continue  # row is unusable
                template = templates[r['template']] = {'policies': {'default_policy': get_default_policy()}}
            updatePolicies(template['policies'], args.type)

    for t in templates:
        new_tpl = copy.deepcopy(tpl)
        new_tpl['time_variate_thresholds_specification']['policies'] = templates[t]['policies']
        new_tpl['identifying_name'] = t
        new_tpl['title'] = t

        #print json.dumps(new_tpl, indent=4)
        id = cfg.create_config("kpi_threshold_template", new_tpl)

        print "created " + str(id)

    # id = cfg.create_config("kpi_threshold_template", tpl)

    # print cfg.list_types()
