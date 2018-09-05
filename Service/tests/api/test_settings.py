"""
Settings database data available (and possibly manipulated) by/for config tests:
    tests/testdata/settings.json
"""

from app.models.utils import get_db
from app.models.settings import Settings
import pytest
import json, logging

# module level logging
logger = logging.getLogger(__name__)

@pytest.fixture(scope="module")
def app(request):
    # module level setup executed before any 'settings' test in current file

    from app import create_app
    app = create_app("config.py")
    app.db = get_db
    app.config["LOGIN_ENABLED"] = False

    # create settings object with default attributes
    s = Settings.load()
    s.save()

    # set client to authenticated user before starting any tests
    app.client = app.test_client()

    # teardown called after all tests in session have completed
    def teardown(): pass
    request.addfinalizer(teardown)

    logger.debug("(settings) module level app setup completed")
    return app


def test_api_read_settings(app):
    # verify read to config returns data (test may not include full config)
    response = app.client.get("/api/settings")
    assert response.status_code == 200
    js = json.loads(response.data)
    js = js["objects"][0]["settings"]
    assert "app_name" in js

def test_api_update_settings(app):
    # update settings disabled
    response = app.client.patch("/api/settings", data=json.dumps({
        "app_name": "new_app_name"
    }), content_type='application/json')
    assert response.status_code == 200

def test_api_delete_settings_rejected(app):
    # delete method to config should be denied (405 - method not allowed)
    response = app.client.delete("/api/settings")
    assert response.status_code == 405  
