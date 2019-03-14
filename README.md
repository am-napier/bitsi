# bitsi
Splunk ITSI script for simple REST calls


itsi.py is needed for everything.  The boiler_plate.py and entity_cleanup.py are examples of what you can do.

simple examples:

Bear with me here, I'll be testing over the next week to make sure this works but due to lack of time and other brown material its not tested now but wanted to get it out there.

    import itsi
    
    cfg = itsi.Config(user="admin", host="localhost", port=8089, pswd="changeme")
    f=itsi.Filter.rex("title", "^foo")
    for e in cfg.read_config('entity', fields='title,_key,identifier,informationaal', filter=f):
       print e
       
    all_objects_filter = itsi.Filter.title(".*")

    # read a service, gets [0]because this is a list function.  Will bomb if there is no service matching the title given
    tpl = cfg.read_config(fields='', filter=itsi.Filter.title("My Service"))[0]
    
    # create a copy of 'My Service'
    tpl['title'] = "My New Service (copy of My Service)"
    cfg.create_config('service', tpl)
    
    # update my new service
    tpl['description'] = "updated description ...."
    cfg.update_config('service', tpl, tpl['_key'])
    
    # CAUTION - deletes ALL your services
    cfg.delete_config("service", filter=all_objects_filter)
    
    # how many items pending in the refresh queue?
    cfg.read_refresh_q_size()

You can read all KV store objects returned by list_types()
You need to know the schema underlying these objects, see the ITSI REST API docs.  http://docs.splunk.com/Documentation/ITSI/latest/RESTAPI/ITSIRESTAPIreference
For bulk updates use the bulk_update_config function
The API is not aware of deep copy, ie you must supply the whole object if you update a section, so read it first and use the read copy.  For the first level its OK (or was at the time of my last test)
This can have dramatic impact on the refresh queue so keep an eye there

requires requests ...

<blurb>Backup your KV store first, no warranties implied or otherwise ... </blurb>
