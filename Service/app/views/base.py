
from ..models.rest import Rest
from ..models.utils import get_user_cookies
from ..models.utils import get_user_data
from ..models.utils import get_user_headers
from ..models.utils import get_user_files
from ..models.utils import get_user_params

from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import redirect
from flask import make_response
from flask import send_from_directory
from six import string_types
from werkzeug.utils import secure_filename

import json
import logging
import os
import re
import requests
import shutil
import traceback
import uuid

logger = logging.getLogger(__name__)
base = Blueprint("base", __name__)

# redirect for base folder to UIAssets folder
@base.route("/")
def base_redirect():
    # check status and only if 200 (ready) redirect to UIAssets
    from ..models.app_status import AppStatus
    (ready, status) = AppStatus.check_status()
    if not ready: return abort(503, status)
    return redirect("/UIAssets/", code=302)

##############################################################################
# proxy API, imported by api module
##############################################################################

@base.route("/proxy", methods=["GET","POST"])
@base.route("/proxy.json", methods=["GET", "POST"])
def aci_app_proxy():
    """ this function is a workaround to current ACI app api restriction that
        only allows for post/get requests and static one-level urls.  Instead
        of doing get/post/delete to dynamic url as provided by this app, 
        the request will be posted to a static 'proxy' url with the following 
        information provided via post data or url params
        Args:
            url(str): original url to perform proxy
            method(str): get, post, or delete (default get)
            data(json): post data to forward to url
            params(json): parameters to forward to url
        Returns:
            json for proxies to api else text response from proxy
    """
    Rest.authenticated()
   
    user_params = get_user_params()
    user_data = get_user_data()
    user_headers = get_user_headers()
    user_cookies = get_user_cookies()
    user_files = get_user_files()

    # args can be provided via params or post data. 
    # If both are provided then post data will be preferred
    method = user_params.get("method", "get").lower()
    url = user_params.get("url", None)
    data = user_params.get("data", {})
    params = user_params.get("params", {})
    # override method/url/data/params found in user data
    if "method" in user_data:
        method = user_data["method"]
    if "url" in user_data:
        url = user_data["url"]
    if "data" in user_data:
        data = user_data["data"]
    if "params" in user_data:
        params = user_data["params"]
   
    # force data from json and back to ensure it's properly formatted 
    if data is not None and type(data) is not dict:
        try: data = json.loads(data)
        except Exception as e: abort(400, "invalid value for 'data'")
    data = json.dumps(data)
    # leave params as dict as required by requests methods
    if params is not None and type(params) is not dict:
        try: params = json.loads(params)
        except Exception as e: abort(400, "invalid value for 'params'")

    # validate url and methods
    if not isinstance(method, string_types):
        abort(400, "invalid value for 'method'")
    if url is None:
        abort(400, "missing required attribute 'url'")
    if not isinstance(url, string_types):
        abort(400, "invalid value for 'url'")
    if not re.search("^/", url):
        abort(400, "invalid value for 'url', must start with / character") 

    method = method.lower()
    url = "%s%s"%(current_app.config.get("PROXY_URL", "http://localhost"),url)
    is_json = "json" in user_headers.get("content-type", "")
    if method == "get":
        r = requests.get(url, verify=False, data=data, params=params, cookies=user_cookies,
                        headers=user_headers)
    elif method == "post":
        if len(user_files)>0:
            files = {}
            tmp_dir = "%s/%s" % (current_app.config["TMP_DIR"], uuid.uuid4())
            tmp_dir = os.path.realpath(tmp_dir)
            try:
                if not os.path.isdir(tmp_dir): os.makedirs(tmp_dir)
                for f in user_files:
                    tmp_file = "%s/%s" % (tmp_dir, secure_filename(user_files[f].filename))
                    user_files[f].save(tmp_file)
                    files[f] = open(tmp_file, "rb")
                    logger.debug("proxy file %s from %s", f, tmp_file)

                # perform post preserving only cookies and override header content type
                r = requests.post(url, verify=False,params=params,cookies=user_cookies,files=files)
            except Exception as e:
                logger.debug("Traceback:\n%s", traceback.format_exc())
                abort(500, "failed to proxy uploaded file: %s" % e)
            finally:
                if os.path.exists(tmp_dir): 
                    shutil.rmtree(tmp_dir)
        else:
            r = requests.post(url, verify=False, data=data, params=params, cookies=user_cookies,
                            headers=user_headers)
    elif method == "patch":
        r = requests.patch(url, verify=False, data=data, params=params, cookies=user_cookies,
                            headers=user_headers)
    elif method == "delete":
        r = requests.delete(url, verify=False, data=data, params=params, cookies=user_cookies,
                            headers=user_headers)
    else:
        abort(400, "invalid value for 'method'")
  
    if r.status_code != 200:
        # try to extract 'error' from non-success json response 
        text = r.text
        try: 
            js = r.json()
            if "error" in js: text = js["error"] 
        except Exception as e: pass
        abort(r.status_code, text)

    # support proxy of downloaded file
    if "Content-Disposition" in r.headers:
        reg = "^attachment; filename=\"?(?P<fname>[^\"]+)\"?"
        r1 = re.search(reg, r.headers["Content-Disposition"], re.IGNORECASE)
        if r1 is not None:
            tmp_file = "%s/%s/%s" % (current_app.config["TMP_DIR"], uuid.uuid4(), r1.group("fname"))
            tmp_file = os.path.realpath(tmp_file)
            tmp_dir = os.path.dirname(tmp_file)
            logger.debug("proxying file %s through tmp file %s", r1.group("fname"), tmp_file)
            try:
                if not os.path.isdir(tmp_dir): 
                    os.makedirs(tmp_dir)
                with open(tmp_file, "wb") as f: 
                    f.write(r.content)
                return send_from_directory(tmp_dir, tmp_file.split("/")[-1], as_attachment = True)
            except Exception as e:
                logger.error("Traceback:\n%s", traceback.format_exc())
                abort(500, "proxy download failed: %s" % e)
            finally:
                if os.path.exists(tmp_dir): 
                    shutil.rmtree(tmp_dir)
    if is_json:
        try: return jsonify(r.json())
        except Exception as e:
            r1 = re.search("https?://[^/]+(?P<clean>.*)", r.url)
            if r1 is not None: clean = r1.group("clean")
            else:clean = r.url
            abort(500, "proxy to (%s)%s failed, received non-json reply" % (method, clean))
    else:
       return make_response(r.text)
