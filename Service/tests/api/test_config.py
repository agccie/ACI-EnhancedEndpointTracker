import json

"""
Settings database data available (and possibly manipulated) by/for config tests:
    tests/testdata/settings.json
"""

def test_api_read_config(app):
    # verify read to config returns data (test may not include full config)
    response = app.client.get("/api/config")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "app_name" in js

def test_api_update_config(app):
    # verify update to config is successful by update followed by read
    response = app.client.post("/api/config", data=json.dumps({
        "app_name": "new_app_name"
    }), content_type='application/json')
    assert response.status_code == 200
    
    # read updated config
    response = app.client.get("/api/config")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "app_name" in js
    assert js["app_name"] == "new_app_name"

def test_api_delete_config_rejected(app):
    # delete method to config should be denied (405 - method not allowed)
    response = app.client.delete("/api/config")
    assert response.status_code == 405  
