
# flask pytest with built-in fixtures documentation
# https://pytest-flask.readthedocs.org/en/latest/features.html#fixtures
# flask test_client
# http://flask.pocoo.org/docs/0.10/api/#flask.Flask.test_client

import pytest
import os, json, sys, subprocess, logging
from pymongo import IndexModel

# testing environmental variables
os.environ["SIMULATION_MODE"] = "1"
os.environ["MONGO_URI"] = "mongodb://localhost:27017/testdb?connectTimeoutMS=100&socketTimeoutMS=10000&serverSelectionTimeoutMS=100"
os.environ["LOGIN_ENABLED"] = "1"
tdir = "tests/testdata/"
db_name = "testdb"

from app.models.users import Users
from app.models.roles import Roles
from app import create_app
# instance relative config - config.py implies instance/config.py
myapp = create_app("config.py")

# set default username and password in config
myapp.config["test_password"] = "cisco"
myapp.testing = True

# setup logging
logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
logger_handler = logging.StreamHandler(sys.stdout)
fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||%(filename)s"
fmt+=":(%(lineno)d)||%(message)s"
logger_handler.setFormatter(logging.Formatter(
    fmt=fmt,
    datefmt="%Z %Y-%m-%dT%H:%M:%S")
)
logger.addHandler(logger_handler)

# test connectivity to database before starting any tests
with myapp.app_context():
    db = myapp.mongo.db
    try: db.collection_names()
    except Exception as e:
        sys.exit("failed to connect to database")

@pytest.fixture(scope="session")
def app(request):
    # setup database with basic config and user. Create session with 
    # authenticated user for any other api test cases to use.
    # (basic app.api.config and view routing for login required...)
    with myapp.app_context():
        db = myapp.mongo.db

        # initialize collection with default values
        init_collection(
            collection_name = "settings",
            collection = db.settings,
            jsfile = "%s/settings.json" % tdir,
        )
        init_collection(
            collection_name = "users",
            collection = db.users,
            jsfile = "%s/users.json" % tdir,
            index = "username"
        )
        init_collection(
            collection_name = "groups",
            collection = db.groups,
            jsfile = "%s/groups.json" % tdir,
            index = "group"
        )
        init_collection(
            collection_name = "rules",
            collection = db.rules,
            jsfile = "%s/rules.json" % tdir,
            index = "dn"
        )
        # ept required database files
        init_collection(
            collection_name = "ep_tunnels",
            collection = db.ep_tunnels,
            jsfile = "%s/ept/ep_tunnels.json" % tdir,
        )
        init_collection(
            collection_name = "ep_nodes",
            collection = db.ep_nodes,
            jsfile = "%s/ept/ep_nodes.json" % tdir,
        )
        init_collection(
            collection_name = "ep_vpcs",
            collection = db.ep_vpcs,
            jsfile = "%s/ept/ep_vpcs.json" % tdir,
        )
        init_collection(
            collection_name = "ep_history",
            collection = db.ep_history,
            # ep_history is directory of files...
            jsfile = "%s/ept/ep_history" % tdir,
            index = ["vnid","addr"]
        )
        init_collection(
            collection_name = "ep_moves",
            collection = db.ep_moves,
            jsfile = "%s/ept/ep_moves.json" % tdir,
            index = ["vnid","addr"]
        )
        init_collection(
            collection_name = "ep_stale",
            collection = db.ep_stale,
            jsfile = "%s/ept/ep_stale.json" % tdir,
            index = ["vnid","addr"]
        )
        init_collection(
            collection_name = "ep_settings",
            collection = db.ep_settings,
            jsfile = "%s/ept/ep_settings.json" % tdir,
            index = "fabric"
        )
        init_collection(
            collection_name = "ep_vnids",
            collection = db.ep_vnids,
            jsfile = "%s/ept/ep_vnids.json" % tdir,
            index = ["fabric","name"],
        )
        init_collection(
            collection_name = "ep_epgs",
            collection = db.ep_epgs,
            jsfile = "%s/ept/ep_epgs.json" % tdir,
            index = ["fabric","name"],
        )
        init_collection(
            collection_name = "ep_subnets",
            collection = db.ep_subnets,
            jsfile = "%s/ept/ep_subnets.json" % tdir,
            index = ["fabric", "vnid"]
        )
        init_collection(
            collection_name = "ep_offsubnet",
            collection = db.ep_offsubnet,
            jsfile = "%s/ept/ep_offsubnet.json" % tdir,
            index = ["vnid","addr"]
        )
        
        # setup admin user independent of import users.json
        init_admin(db)

    # teardown called after all tests in session have completed
    def teardown(): pass
    request.addfinalizer(teardown)
    return myapp

def init_collection(**kwargs):
    """ initialize collection by dropping it and then inserting test data
        stored in jsfile.  If index is specified, create collection with
        specified index as unique
    """
    collection_name = kwargs.get("collection_name", None)
    collection = kwargs.get("collection", None)
    jsfile = kwargs.get("jsfile", None)
    index = kwargs.get("index", None)

    if collection is not None:
        collection.drop()

    if jsfile is not None and collection_name is not None and \
        db_name is not None:

        # if jsfile is a directory, then loop through directory
        files = []
        if os.path.isdir(jsfile):
            for f in os.listdir(jsfile): 
                p = "%s/%s" % (jsfile, f)
                if "json" in f and not os.path.isdir(p): files.append(p) 
        elif os.path.exists(jsfile):
            files.append(jsfile)

        for f in files:
            cmd = "mongoimport --db %s --collection %s --file %s --jsonArray"%(
                    db_name, collection_name, f)
            try:
                p = subprocess.Popen((cmd).split(" "), stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                p.wait()    # wait for child process to terminate
            except Exception as e:
                raise Exception("import exception: %s, file:%s, cmd: %s" % (
                    e, f, cmd))

    if index is not None and collection is not None:
        if type(index) is list:
            collection.create_indexes([IndexModel(i) for i in index])
        else:
            collection.create_index(index, unique=True)


def init_admin(db):
    """ ensure admin user exists even if not in seed data.  Ensure admin
        is full admin with password of myapp.config
    """
    
    # check if user 'admin' exists, if so delete it and manually create it
    r = db.users.find({"username":"admin"})
    if r.count()>0: db.users.delete_one({"username":"admin"})

    db.users.insert_one({
        "username": "admin",
        "password": Users.hash_pass(myapp.config["test_password"]),
        "role": Roles.FULL_ADMIN
    })

    # use test client to confirm login is successful (since most api tests
    # are dependent on successfully login of 'admin' user)
    myapp.client = myapp.test_client()
    response = myapp.client.post("api/login", data=json.dumps({
        "username":"admin",
        "password":myapp.config["test_password"]
    }), content_type='application/json', follow_redirects=True)
    # stop all testing if basic login fails
    assert response.status_code == 200

