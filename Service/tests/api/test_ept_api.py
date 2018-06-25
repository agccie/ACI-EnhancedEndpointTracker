import json
from app.tasks.ept import utils as ept_utils

def generic_action(app, url, **kwargs):
    # perform a get/post/delete option and check for expected status
    # assert if status does not match expected status.  return reply 
    method = kwargs.get("method", "get").lower()
    expected_status = kwargs.get("status", 200)
    data = kwargs.get("data", {})
    if method == "get":
        response = app.client.get(url)
    elif method == "post":
        response = app.client.post(url, data=json.dumps(data), 
                                    content_type = "application/json")
    elif method == "delete":
        response = app.client.delete(url, data=json.dumps(data), 
                                    content_type = "application/json")
    js = json.loads(response.data)
    if response.status_code != expected_status:
        # print reply before assertion to ensure we capture it in the log
        print "Unexpected status code: [%s!=%s]" % (response.status_code,
            expected_status)
        print "reply: %s" % ept_utils.pretty_print(js)
        assert response.status_code == expected_status
    return js

def test_api_read_ept_settings(app):
    # verify read to config returns data (test may not include full config)
    url = "/api/ept/settings"
    js = generic_action(app, url, method="get")
    assert "ep_settings" in js

def test_api_write_trust_subscription_option(app):
    # verify write to trust_subscripton supports 'yes' option
    url = "/api/ept/settings"
    fab_name = "trust_subscription"
    
    # create fabric
    generic_action(app, url, method="post", data = {
        "fabric": fab_name,
    })

    # valid options yes/no/auto 
    for opt in ["yes", "no", "auto"]:
        js = generic_action(app, url+"/"+fab_name, method="post", data={
            "trust_subscription": opt
        })
        js = generic_action(app, url+"/"+fab_name)
        assert js["trust_subscription"] == opt
    # invalid option
    generic_action(app, url+"/"+fab_name, method="post", status=400, data={
        "trust_subscription": "invalid_option"
    })

