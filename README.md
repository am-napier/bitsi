# bitsi
Splunk ITSI script for simple REST calls

itsi.py and logger.py are needed for everything.  The boiler_plate.py and entity_cleanup.py are examples of what you can do.

simple example:

    import itsi, json
    from logger import log
    
    cfg = itsi.Config()
    cfg.setUser(user)     # default is "admin"
    cfg.setHost(server)   # default is "localhost"
    cfg.setPort(port)     # default is "changeme", if you use boiler plate and call setup call be promted for this
    cfg.setPswd(pswd)     # default 8089, note its an int

    # there is also a Filter.title method but this is a more interesting example, you can also use identifier.fields etc..
    f=itsi.Filter.rex("title", "^foo")
    
    for e in cfg.doRead('entity', fields='title,_key,identifier,informationaal', filter=f):
       log.info(e, indent=4)
        
    # disclaimer: I didn't test this example, but I've been using this itsi script though for nearly 2 years.

You can read all KV store objects returned by list_types()
You need to know the schema underlying these objects, see the ITSI REST API docs.  http://docs.splunk.com/Documentation/ITSI/latest/RESTAPI/ITSIRESTAPIreference
For bulk updates use the bulk_update function
The API is not aware of deep copy, ie you must supply the whole object if you update a section, so read it first and use the read copy.  For the first level its OK (or was at the time of my last test)
This can have dramatic impact on the refresh queue so keep an eye there

requires requests ...

<blurb>Backup your KV store first, no warranties implied or otherwise ... </blurb>
