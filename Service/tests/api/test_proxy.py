
from app import create_app
from app.models.rest import api_register
from app.models.rest import api_route
from app.models.rest import Rest
from app.models.rest import Universe
from app.models.utils import get_app_config
from app.models.utils import get_db
from app.models.utils import pretty_print
from app.models.aci.utils import run_command
from app.models.aci.utils import terminate_process
from app.models.aci.utils import terminate_pid
from flask import send_from_directory
from multiprocessing import Process
import json
import logging
import os
import pytest
import re
import shutil
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

PROXY_PORT = 7272

proxy_url = "/api/test/proxy"
testdata = os.path.realpath("%s/../../testdata/" % __file__)

# Test class regisetered with API
@api_register(path="test/proxy")
class Rest_TestProxy(Rest):
    META_ACCESS = {}
    META = {
        "key": {
            "key": True,
            "type": str,
        },
    }

    @classmethod
    @api_route(path="upload", methods=["POST"])
    def upload(cls):
        from flask import abort, current_app, jsonify, request
        # receive uploaded file and save to tmp directory
        cls.logger.debug("handle test upload")
        config = {}
        with current_app.app_context(): config = current_app.config
        for filename in request.files:
            f = request.files[filename]
            dst = os.path.realpath("%s/%s" % (config["TMP_DIR"], f.filename))
            logger.debug("saving to %s", dst)
            f.save(dst)
            return jsonify({"success":True})
        abort(400, "no file found")

    @classmethod
    @api_route(path="download", methods=["GET"])
    def download(cls):
        # send download file 'download.txt'
        from flask import current_app
        config = {}
        with current_app.app_context(): config = current_app.config
        download = "download.txt"
        cls.logger.debug("download: %s from %s", download, config["TMP_DIR"])
        return send_from_directory(config["TMP_DIR"], download, as_attachment = True)

def run_proxy_app(proxy_app):
    # run app on arbitray port to serve proxy requests
    logger.debug("%s running proxy app on port %s", "-"*80, PROXY_PORT)

    # get absolute path for top of app
    p = os.path.realpath(__file__)
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    os.chdir(p)
    cmd = "python run.py --test -p %s" % PROXY_PORT
    os.system(cmd)
    logger.error("proxy app killed")

def kill_group(pid):
    # run_proxy_app will have multiple child processes, we need to find and kill all of them
    tree = {0:{}}
    mapped_pids = {0: tree}         # mapping of id to point in pids tree
    pid_pairs = []                  # list of unmapped tuplies (parent, child)
    logger.debug("kill group for pid %s", pid)
    output = run_command("ps -e -o pid,ppid")
    if output is not None:
        for l in output.split("\n"):
            r1 = re.search("^[ ]*(?P<pid>[0-9]+)[ ]*(?P<ppid>[0-9]+)", l.strip())
            if r1 is not None:
                pid_pairs.append((int(r1.group("ppid")), int(r1.group("pid"))))
        def build_tree(node, search):
            pop = []
            for p in pid_pairs:
                if p[0] == search: 
                    node[p[1]] = {}
                    mapped_pids[p[1]] = node[p[1]]
                    pop.append(p)
            for p in pop: pid_pairs.remove(p)

            # add children to pids we just found
            for pid in node:
                build_tree(node[pid], pid)

        def get_children(node):
            # get list of pids that are children or grandchildren of this node ordered by 
            # grandchildren first
            result = []
            for p in node:
                result+= get_children(node[p])
                result.append(p)
            return result

        logger.debug("running processes:\n%s", output)
        build_tree(tree[0], 0)
        logger.debug("pid tree:\n%s", pretty_print(tree))
        if len(pid_pairs)>0:
            logger.error("subset of pids not matched in pid tree: %s", pid_pairs)
        if pid not in mapped_pids:
            logger.error("failed to find pid(%s) in mapped tree", pid)
        else:
            for p in get_children(mapped_pids[pid]):
                logger.debug("killing pid: %s", p)
                terminate_pid(p)
    else:
        logger.error("failed to read pids - proxy app may still be running...")

@pytest.fixture(scope="module")
def app(request, app):
    # module level setup executed before any 'user' test in current file
    logger.debug("%s module-prep start", "-"*80)

    app.config["LOGIN_ENABLED"] = False
    t_app = create_app("config.py")
    t_app.db = get_db()
    t_app.client = t_app.test_client()
    t_app.config["LOGIN_ENABLED"] = False
    t_app.config["PROXY_URL"] = "http://127.0.0.1:%s" % PROXY_PORT
    t_app.config["TMP_DIR"] = os.path.realpath("%s/test" % t_app.config["TMP_DIR"])

    # create test directory if not present
    if not os.path.isdir(t_app.config["TMP_DIR"]):
        os.makedirs(t_app.config["TMP_DIR"])

    # copy testdata files to /tmp/ directory before tests start
    testfiles = [
        "%s/download.txt" % testdata,
    ]
    logger.debug("copying testdata files to tmp directory")
    for tf in testfiles:
        dst = re.sub("//", "/", "%s/%s" % (t_app.config["TMP_DIR"], tf.split("/")[-1]))
        logger.debug("copying testfile from %s to %s", tf, dst)
        if not os.path.exists(dst): shutil.copy(tf, dst)

    logger.debug("setting up proxy server")
    proxy_server = Process(target=run_proxy_app, args=(t_app,))
    proxy_server.start()
    # give the server a second to start
    logger.debug("waiting for proxy server to start")
    time.sleep(2)

    # ensure uni exists
    uni = Universe()
    assert uni.save()

    # teardown called after all tests in session have completed
    def teardown(): 
        logger.debug("%s module-prep teardown", "-"*80)
        if proxy_server.is_alive(): 
            logger.debug("terminating proxy server (%s)", proxy_server.pid)
            kill_group(proxy_server.pid)
            terminate_process(proxy_server)
        shutil.rmtree(t_app.config["TMP_DIR"])

    request.addfinalizer(teardown)

    logger.debug("(proxy) module level app setup completed")
    return t_app


@pytest.fixture(scope="function")
def funcprep(request, app):
    # function level bring up and teardown
    logger.debug("%s funcprep start", "*"*80)
    def teardown():
        logger.debug("%s funcprep tear down", "-"*80)
        # kill proxy_server
        Rest_TestProxy.delete(_filters={})

    request.addfinalizer(teardown)
    logger.debug("********** funcprep completed")
    return
       
def test_proxy_read(app, funcprep):
    # send proxy read request and ensure data is captured

    # first read no objects found
    logger.debug("test proxy request")
    c = app.test_client()
    response = c.get("/proxy.json?url=/api/test/proxy")
    assert response.status_code == 200
    js = json.loads(response.data)
    logger.debug(js)
    assert js["count"] == 0 and len(js["objects"]) == 0

    # second read should have one object
    Rest_TestProxy.load(key="key1").save()
    response = c.get("/proxy.json?url=/api/test/proxy")
    assert response.status_code == 200
    js = json.loads(response.data)
    logger.debug(js)
    assert js["count"] == 1 and len(js["objects"]) == 1

def test_proxy_download(app, funcprep):
    # ensure download through proxy works
    
    c = app.test_client()
    response = c.get("/proxy.json?url=/api/test/proxy/download")
    logger.debug(response.headers)
    hstr = "%s" % response.headers
    assert response.status_code == 200
    assert "Content-Disposition" in hstr and "filename" in hstr and "download.txt" in hstr

def test_proxy_upload(app, funcprep):
    # ensure upload through proxy works - check that uploaded file is in tmp/test directory

    f = open("%s/upload.txt" % testdata, "rb")
    c = app.test_client()
    response = c.post("/proxy.json?url=/api/test/proxy/upload&method=POST",
        data = {"file": (f, "upload.txt")}
    )
    assert response.status_code == 200
    # ensure that file was actually saved to tmp directory
    assert os.path.exists("%s/%s" % (app.config["TMP_DIR"], "upload.txt"))

