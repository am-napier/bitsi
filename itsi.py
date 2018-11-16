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
	for i in r.listTypes():
		try:
			res.append( "Count of %s is %d" % (i, r.getCount(i)) )
		except ItsiError as e:
			res.append('Failed: ' + e.text)
 
	for i in res:
		print i


'''

import requests, csv, io, sys, uuid, json, copy
from requests.auth import HTTPBasicAuth
from logger import log
#requests.packages.urllib3.disable_warnings()

from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.packages.urllib3.exceptions import SNIMissingWarning
from requests.packages.urllib3.exceptions import InsecurePlatformWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
requests.packages.urllib3.disable_warnings(SNIMissingWarning)
requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)


class Config:
	user = 'admin'
	pswd = 'changeme'
	host = 'localhost'
	port = 8089
	templateCache = {}

	def __init__(self):
		self.session = requests.Session()
		self.session.auth = (self.user, self.pswd)

	def setUser(self, user):
		self.user = user
		self.session.auth = (self.user, self.pswd)

	def setPswd(self, pswd):
		self.pswd = pswd
		self.session.auth = (self.user, self.pswd)

	def setHost(self, host):
		self.host = host

	def setPort(self, port):
		self.port = port


	'''
	Get a count of the objects that are of the given type and match the specified filter
	
	examples
	cfg = ITSIConfig() #assume the default creds are OK
	cfg.getCount()	<= returns the number of services defined
	cfg.getCount(type='entity')	<= returns the number of entities defined
	cfg.getCount(type='entity', filter='"title" : {"$regex":"^app|bah$", "$options":"i"}}')	<= returns the number of entities defined that have a title string with app or ending in bah
	
	returns int
	raises ItsiError if it failed
	'''
	def getCount(self, type='service', filter=''):
		params = []
		if filter != '':
			params.append("filter=%s" % filter)		

		return self._getJsonOrDie(self.session.get(self._getURL([type, 'count'], params), verify=False))['count']
	

	'''
	Get all the types supported by the API
	Will return a list of available types to manage
	'''
	def listTypes(self):
		return self._getJsonOrDie(self.session.get(self._getURL(['get_supported_object_types']), verify=False))


	''' -----------------------------------------------------------------
	json[] doRead - read all the objects from the nominated server using the filter/fields provided
			
	Params:
		limit - number of rows to return, 0 is all records and the default value
		filter - mongodb filter to include records
		fields - csv list of fields to return

	examples:
	
	List the services
		r.doRead()

	List the entities	
		r.doRead('entity')	

	List the entities that start with host and get the title, _key, _user and informational fields	
		r.doRead('entity', filter='{"title":{"$regex":"^host"} }', fields='title,_key,_user,informational')	

	return json[]	
	'''
	def doRead(self, type="service", key='', filter='', fields='title,_key', limit=0):
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

		return self._getJsonOrDie(self.session.get(self._getURL(uris, params), verify=False))

	'''
	read a template object for the service using the title provided
	we could cache this if its too slow and return a copy of what is in the cache because the 
	caller WILL modify the object.
	This works for services and kpi_base searches only, its a limit of the API.
	'''
	def getTemplate(self, uuid, type="service"):
                uris = [type, uuid, "templatize"]
                return self._getJsonOrDie(self.session.get(self._getURL(uris), verify=False))
		# setup the blank cache
		try:	
			if uuid not in self.templateCache[type]:
				# not in the cache so get a copy and store it
				uris = [type, uuid, "templatize"]
				self.templateCache[type][uuid] = self._getJsonOrDie(self.session.get(self._getURL(uris), verify=False))
			# dont return the copy in the cache (in case the caller modifies it) but make a copy for return
			res = copy.deepcopy(self.templateCache[type][uuid])
			# fix the kpis adds uuids and removes the service health kpi as that seems to be added back in when its committed
			self.fixKPIs(res)
			return res
			
		except KeyError:
			# means the key for type hasn't been created before
			log.info("getTemplate::creating cache for " + type)
			self.templateCache[type] = {}

		return self.getTemplate(uuid, type)


	'''
	Don't allow blank filter unless key is specified, one MUST have a value so accidental deletes on all objects cant happen
	complete deletes don't happen
	return int number of deletes run

	testing for this will check to see ...
	'''	
	def doDelete(self, type, key='', filter=''):
		# if filter=='' and key=='':
		# 	raise ItsiError('key and filter are blank, please supply one value or all objects will be deleted')

		# return self._getJsonOrDie(self.session.delete(self._getURL([type], _getParams(filter=filter, key=key)), verify=False))

		uris = [type]
		if key=='' and filter=='':
			raise ItsiError('key and filter are blank, please supply one value or all objects of this type will be deleted')
		elif key!= '' :
			uris.append(key)
		# note is_partia_data requred to stop overwrite of existing properties
		url = self._getURL(uris, ["filter=%s" % (filter)])
		log.info("Delete URL = "+url)
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
	def doUpdate(self, type, template, key):
		#log.db("doMod ... ")
		uris = [type, key]
	
		return self._getJsonOrDie(self.session.post(self._getURL(uris, ['is_partial_data=1']), json.dumps(template), verify=False, headers={'Content-Type':'application/json'}))

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

	def doBulkUpdate(self, type, data):
		# log.db("doMod ... ")
		uris = [type, "bulk_update"]

		return self._getJsonOrDie(
			self.session.post(self._getURL(uris, ['is_partial_data=1']), json.dumps(data), verify=False,
							  headers={'Content-Type': 'application/json'}))


	'''
	type is the ITSI object type
	template is an object that implements the getConfig() method for the type requested
	return key UUID of new object created

	json.dumps seems to be needed to force the dict to json before sending	
	'''
	def doCreate(self, type, template):
		# this could fail if UUIDs are not managed
		return self._getJsonOrDie(self.session.post(self._getURL([type], []), json.dumps(template), verify=False, headers={'Content-Type':'application/json'}))

# 	'''
# 	replace the alias called name with the parameter value in the passed ruleArray
# 	assumes dict is the entity_rules array defined on a service object from doRead or getTemplate
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
	def addUUIDs(self, svc):
		for k in svc['kpis']:
			k['_key'] = self._getUUID()

	# this is a destructive method and WILL change the contents of svc in two ways
	# 1. the service_health KPI will be removed because if it exists in the template when we create it then it gets added twice (log that bug)
	# 2. there are no UUIDs assigned for the KPIs so add them (log that enhancement)

	# would be nicer if this returned a modified copy instead, then changes would not impact the original
	# im thinking for performance that we'll need a caching layer on the templates so we don't have to read them
	# them from the server every time we want one because its two API calls

	def fixKPIs(self, svc):
		# fix the UUIDs cause there aren't any set
		# remove the service health KPI or it gets created twice
		self.addUUIDs(svc)
		kpis = []
		for kpi in svc['kpis']:
			if kpi['type'] != "service_health":
				kpi['_key'] = self._getUUID()
				kpis.append(kpi)
		svc['kpis'] = kpis

	# --------------------------------------------------------------------------
	# --------------------------------------------------------------------------
	# -----------------  Private functions used in this module -----------------

	# this doesn't guarentee it created a unique UUID
	def _getUUID(self):
		return str(uuid.uuid4())

	'''
	Get the url to run the job
	'''
	def _getURL(self, uri=[], params=[]):
		url = "https://%s:%d/servicesNS/nobody/SA-ITOA/itoa_interface/%s?%s" % (self.host, self.port, "/".join(uri), "&".join(params))
		log.db("_getURL ==>>> "+url)
		return url

	'''
	Gets a json response from the Response passed in or return an ItsiError

	@todo: this needs more testing, not confident it works under all the conditions it might be called due to the many
	different exceptions that can be raised, see http://docs.python-requests.org/en/master/_modules/requests/exceptions/
	
	'''
	def _getJsonOrDie(self, resp):
		try:
			resp.raise_for_status()
			return resp.json()
		except requests.exceptions.RequestException as re:
			raise ItsiError(resp.text, re)
		except Exception as e:
		    raise ItsiError("Base error: "+resp.text, e)

'''
more design work needed here too ...
''' 
class ItsiError(Exception):
	ok = False	# use this the same way as the response.ok can be used.
	def __init__(self, text, chained=None):
		self.text = "ItsiError: "+str(text)
		if( chained != None ):
			self.base = chained
			self.text += str(chained)

		log.err("Raised ITSI Error: "+self.text)


class Filter:
	def __init__(self):
		pass

	'''
	get a filter for a title or regex to query the KV store, 
	details are here https://docs.mongodb.com/manual/reference/operator/query/regex/ (ish)
	I found some inconsistencies with the docs when I first did this (re double quotes) and the syntax for the filter 
	was rather fiddley

	call these guys when you need to create a filter for doRead (and maybe others)
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
		return res

	@staticmethod
	def title(val):
		res = '{"title" : "%s" }' % (val)
		return res



def main(args):
	print "running unit tests?"
	r = Config()
	res = []
	print Filter.rex("xxx", "yyy")
	foo.bar()
	for i in r.listTypes():
		try:
			res.append( "Count of %s is %d" % (i, r.getCount(i)) )
		except ItsiError as e:
			res.append('Failed: ' + e.text)
 
	for i in res:
		print i


if __name__ == '__main__':
    main(sys.argv[1:])
