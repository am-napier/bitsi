'''
**ITSIConfig**

The following class can be used to manipulate ITSI objects via its REST interface.

The REST interface is documented here: http://docs.splunk.com/Documentation/ITSI/latest/Configure/ITSIRESTAPIreference

This implementation focuses on just the itoa_interface allowing Create, Delete, Read and Modify operations against
instances of objects (identified by GUID keys) or sets of objects identified by (mongo) filters.

The implementation is session based so setup the user authentication attributes at the start then call various set and do methods documented below

**Note on mongo filters.**
These are tricky little critters to get right and seem to depend upon the language implemntation.
For python the following seems to work.  In the ITSI docs the filter property must appear as filter={"prop_name" : "prop_vale"} but to
easy the syntax

this is required for a title exact match {"title":"EXACT_STR"}
for some regex its thorny => {"title":{"$regex":"^app|bah$", "$options":"i"}}

Todo: add support for 
#. Maintenance Services Interface
#. Backup Restore Interface
#. Event Management Interface

example to list a count of all types:
Note: the try clause is needed as the saved_page type throws a 400 erro 
	from itsi import Config
	r = Config()
	res = []
	for i in r.list_types():
		try:
			res.append( "Count of %s is %d" % (i, r.get_count(i)) )
		except ItsiError as e:
			res.append('Failed: ' + e.text)
 
	for i in res:
		print i


'''

import requests, csv, io, sys, uuid, json, copy, logging
from requests.auth import HTTPBasicAuth

from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.packages.urllib3.exceptions import SNIMissingWarning
from requests.packages.urllib3.exceptions import InsecurePlatformWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
requests.packages.urllib3.disable_warnings(SNIMissingWarning)
requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)

logging_on = False


class Config:
	user = 'admin'
	pswd = 'changeme'
	host = 'localhost'
	port = 8089
	templateCache = {}

	logger = logging.getLogger("splunk.bitsi.Config")

	def __init__(self, host=None, user=None, port=None, pswd=None):
		self.session = requests.Session()

		self.logger.info("logging_on "+str(logging_on))

		if host:
			self.set_host(host)
		if user:
			self.set_user(user)
		if port:
			self.set_port(port)
		if pswd:
			self.set_pswd(pswd)
		self.session.auth = (self.user, self.pswd)

	def set_user(self, user):
		self.logger.debug("set user %s", user)
		self.user = user
		self.session.auth = (self.user, self.pswd)

	def set_pswd(self, pswd):
		self.logger.debug("set user ****")
		self.pswd = pswd
		self.session.auth = (self.user, self.pswd)

	def set_host(self, host):
		self.logger.debug("set host %s", host)
		self.host = host

	def set_port(self, port):
		self.logger.debug("set user %d", port)
		self.port = port


	'''
	Get a count of the objects that are of the given type and match the specified filter
	
	examples
	cfg = ITSIConfig() #assume the default creds are OK
	cfg.get_count()	<= returns the number of services defined
	cfg.get_count(type='entity')	<= returns the number of entities defined
	cfg.get_count(type='entity', filter='"title" : {"$regex":"^app|bah$", "$options":"i"}}')	<= returns the number of entities defined that have a title string with app or ending in bah
	
	returns int
	raises ItsiError if it failed
	'''
	def get_count(self, type='service', filter=''):
		params = []
		if filter != '':
			params.append("filter=%s" % filter)		

		return self._get_json_or_die(self.session.get(self._get_url([type, 'count'], params), verify=False))['count']
	

	'''
	Get all the types supported by the API
	Will return a list of available types to manage
	'''
	def list_types(self):
		return self._get_json_or_die(self.session.get(self._get_url(['get_supported_object_types']), verify=False))


	''' -----------------------------------------------------------------
	json[] read_config - read all the objects from the nominated server using the filter/fields provided
			
	Params:
		limit - number of rows to return, 0 is all records and the default value
		filter - mongodb filter to include records
		fields - csv list of fields to return

	examples:
	
	List the services
		r.read_config()

	List the entities	
		r.read_config('entity')	

	List the entities that start with host and get the title, _key, _user and informational fields	
		r.read_config('entity', filter='{"title":{"$regex":"^host"} }', fields='title,_key,_user,informational')	

	return json[]	
	'''
	def read_config(self, type="service", key='', filter='', fields='title,_key', limit=0):
		params = []
		uris = [type]
		if( len(key) > 0 ):
			uris.append(key)

		if( len(fields) > 0 ):
			params.append("fields="+fields)
		if( limit > 0 ):
			params.append("limit=%d" % limit)
		if filter != '':
			params.append("filter=%s" % (filter))

		return self._get_json_or_die(self.session.get(self._get_url(uris, params), verify=False))

	'''
	read a template object for the service using the title provided
	we could cache this if its too slow and return a copy of what is in the cache because the 
	caller WILL modify the object.
	This works for services and kpi_base searches only, its a limit of the API.
	'''
	def get_template(self, uuid, type="service"):
		uris = [type, uuid, "templatize"]
		return self._get_json_or_die(self.session.get(self._get_url(uris), verify=False))

	def get_refresh_q_size(self):
		url = "https://%s:%d/servicesNS/nobody/SA-ITOA/storage/collections/data/itsi_refresh_queue" \
				% (self.host, self.port)
		try:
			q = self._get_json_or_die(self.session.get(url, verify=False))
			return len(q)
		except Exception as e:
			self.logger.error("Failed to fetch the queue: " + str(e))
		return -1

	'''
	Don't allow blank filter unless key is specified, one MUST have a value so accidental deletes on all objects cant happen
	complete deletes don't happen
	return int number of deletes run

	testing for this will check to see ...
	'''	
	def delete_config(self, type, key='', filter=''):
		uris = [type]
		if key == '' and filter == '':
			raise ItsiError('key and filter are blank, please supply one value or all objects of this type will be deleted')
		elif key != '':
			uris.append(key)
		url = self._get_url(uris, ["filter=%s" % (filter)])
		self.logger.info("Delete URL = " + url)
		return self.session.delete(url, verify=False).ok

	'''
	Provides method to update a single object (by key) or a set (by filter)
	return bool if successful, raises ItsiError if it fails
	if key is supplied then filter is ignored
	if key and filter are blank raises an error (don't allow accidental update for all attributes).  To achieve this provide a filter that matches everything.


	example: change readonly KPI base searches to editable
	doModify('kpi_base_search', {'_immutable' : '0', 'title' : 'DA-ITSI-APPSERVER:Performance.Runtime'}, key='DA-ITSI-APPSERVER:Performance.Runtime' )

	this example can update an entity but to do so without all the original properties will see attributes lost
	doModify('entity', {'description' : 'I can update any property'}, key='df713236-ee1f-427b-af87-73828b512461')
	'''
	def update_config(self, type, template, key):
		uris = [type, key]
	
		return self._get_json_or_die(self.session.post(self._get_url(uris, ['is_partial_data=1']), json.dumps(template), verify=False, headers={'Content-Type': 'application/json'}))

	'''
	Provides method to update a single object (by key) or a set (by filter)
	return bool if successful, raises ItsiError if it fails
	if key is supplied then filter is ignored
	if key and filter are blank raises an error (don't allow accidental update for all attributes).  To achieve this provide a filter that matches everything.


	example: change readonly KPI base searches to editable
	doModify('kpi_base_search', {'_immutable' : '0', 'title' : 'DA-ITSI-APPSERVER:Performance.Runtime'}, key='DA-ITSI-APPSERVER:Performance.Runtime' )

	this example can update an entity but to do so without all the original properties will see attributes lost
	doModify('entity', {'description' : 'I can update any property'}, key='df713236-ee1f-427b-af87-73828b512461')
	'''

	def bulk_update_config(self, type, data):
		uris = [type, "bulk_update"]

		return self._get_json_or_die(
			self.session.post(self._get_url(uris, ['is_partial_data=1']), json.dumps(data), verify=False,
							  headers={'Content-Type': 'application/json'}))


	'''
	type is the ITSI object type
	template is an object that implements the getConfig() method for the type requested
	return key UUID of new object created

	json.dumps seems to be needed to force the dict to json before sending	
	'''
	def create_config(self, type, template):
		# this could fail if UUIDs are not managed
		return self._get_json_or_die(self.session.post(self._get_url([type], []), json.dumps(template), verify=False, headers={'Content-Type': 'application/json'}))

# 	'''
# 	replace the alias called name with the parameter value in the passed ruleArray
# 	assumes dict is the entity_rules array defined on a service object from read_config or get_template
# 	loop through all rule_items and replace text in any with the values provided
# 	ruleType is one of alias, info or title
# 	ruleArray = [
# 		{
# 			"rule_condition": "AND", 
# 			"rule_items": [
# 				{
# 					"rule_type": "matches", 
# 					"field_type": "alias", 
# 					"value": "ONE", 
# 					"field": "Name"	

# 	OR
	
# [{"rule_condition: u'AND', u'rule_items': [{u'rule_type': u'matches', u'field_type': u'title', u'value': u'EIGHT', u'field': u'title'}]}, {u'rule_condition': u'AND', u'rule_items': [{u'rule_type': u'matches', u'field_type': u'title', u'value': u'NINE', u'field': u'title'}]}, {u'rule_condition': u'AND', u'rule_items': [{u'rule_type': u'matches', u'field_type': u'title', u'value': u'FIVE', u'field': u'title'}]}]				
# 	'''	
# 	def updateEntityRule(self, name, value, ruleArray, ruleType='alias'):
# 		for rules in ruleArray:
# 			for rule in rules['rule_items']:
# 				if rule['field_type'] == ruleType and rule['field'] == name:
# 					rule['value'] = value

	# add UUIDs to the KPIs in a service
	# no guarentee the UUIDs are unique so the call could fail when its commited
	# if that happens resubmit
	def add_uuids(self, svc):
		for k in svc['kpis']:
			k['_key'] = self._get_uuids()

	# this is a destructive method and WILL change the contents of svc in two ways
	# 1. the service_health KPI will be removed because if it exists in the template when we create it then it gets added twice (log that bug)
	# 2. there are no UUIDs assigned for the KPIs so add them (log that enhancement)

	# would be nicer if this returned a modified copy instead, then changes would not impact the original
	# im thinking for performance that we'll need a caching layer on the templates so we don't have to read them
	# them from the server every time we want one because its two API calls

	def fix_kpis(self, svc):
		# fix the UUIDs cause there aren't any set
		# remove the service health KPI or it gets created twice
		self.add_uuids(svc)
		kpis = []
		for kpi in svc['kpis']:
			if kpi['type'] != "service_health":
				kpi['_key'] = self._get_uuids()
				kpis.append(kpi)
		svc['kpis'] = kpis

	# --------------------------------------------------------------------------
	# --------------------------------------------------------------------------
	# -----------------  Private functions used in this module -----------------

	# this doesn't guarentee it created a unique UUID
	def _get_uuids(self):
		return str(uuid.uuid4())

	'''
	Get the url to run the job
	'''
	def _get_url(self, uri=[], params=[]):
		url = "https://%s:%d/servicesNS/nobody/SA-ITOA/itoa_interface/%s?%s" % (self.host, self.port, "/".join(uri), "&".join(params))
		self.logger.debug("_get_url ==>>> " + url)
		return url

	'''
	Gets a json response from the Response passed in or return an ItsiError

	@todo: this needs more testing, not confident it works under all the conditions it might be called due to the many
	different exceptions that can be raised, see http://docs.python-requests.org/en/master/_modules/requests/exceptions/
	
	'''
	def _get_json_or_die(self, resp):
		try:
			resp.raise_for_status()
			return resp.json()
		except requests.exceptions.RequestException as re:
			raise ItsiError(resp.text, re)
		except Exception as e:
			raise ItsiError("Base error: "+resp.text, e)


class ItsiError(Exception):
	"""
	more work needed here too ...
	"""

	ok = False         # use this the same way as the response.ok can be used.

	def __init__(self, text, chained=None):
		self.text = "ItsiError: "+str(text)
		self.logger = logging.getLogger("splunk.bitsi.ItsiError")
		if chained is not None:
			self.base = chained
			self.text += str(chained)

			self.logger.error("Raised ITSI Error: " + self.text)


class Filter:
	logger = logging.getLogger("splunk.bitsi.Filter")

	def __init__(self):
		pass

	'''
	get a filter for a title or regex to query the KV store, 
	details are here https://docs.mongodb.com/manual/reference/operator/query/regex/ (ish)
	I found some inconsistencies with the docs when I first did this (re double quotes) and the syntax for the filter 
	was rather fiddly

	call these guys when you need to create a filter for read_config (and maybe others)
	example: 
		from itsi import Filter as F
		titleFilter = F.title("my_service_name")
		rexFilter = F.rex("^my.*", "i")

	Final note : title is solid but rex might give you issues
	'''
	@staticmethod
	def rex(prop, val, flags=''):

		_flgs = ''
		if len(flags) > 0:
			_flgs = ', {"$options" : "%s"}' % (flags)
		res = '{"%s" : {"$regex":"%s"} %s}' % (prop, val, _flgs)
		Filter.logger.info("created regex filter %s", res)
		return res

	@staticmethod
	def title(val):
		res = '{"title" : "%s" }' % (val)
		Filter.logger.info("created title filter %s", res)
		return res


def setup_logging(level='info',
			fmt = '%(asctime)s %(levelname)s [%(lineno)d:%(module)s:%(funcName)s:%(name)s] >> %(message)s'):
	lvl = getattr(logging, level.upper(), getattr(logging, "WARN"))
	logging.basicConfig(level=lvl, format=fmt)
	logging.warn("Setting log level to %s", level)
	logging_on = True


def test_AssertTrue():
	assert True

def test_AssertEquals():
	assert "Foo" == "Foo"

def main(args):
	# filename='myapp.log'
	logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s')

	cfg = Config()
	cfg.set_host("itsiaws")
	print cfg.get_refresh_q_size()
	print "done"


if __name__ == '__main__':
    main(sys.argv[1:])
