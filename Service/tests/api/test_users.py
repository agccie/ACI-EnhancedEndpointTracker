
import json, logging, time
import pytest
from app.models.utils import get_db, pretty_print
from app.models.rest import Role, Universe
from app.models.rest.user import User, Session
from app.models.rest.settings import Settings

keyed_url = "/api/uni/username-{}"
login_url = "/api/user/login"
logout_url = "/api/user/logout"
pwreset_url = "/api/user/pwreset"
keyed_pwreset_url = "%s/pwreset" % keyed_url

# module level logging
logger = logging.getLogger(__name__)

@pytest.fixture(scope="module")
def app(request, app):
    # module level setup executed before any 'user' test in current file

    from app import create_app
    app = create_app("config.py")
    app.config["test_password"] = "password"
    app.db = get_db()
    app.config["LOGIN_ENABLED"] = True

    # ensure uni exists
    uni = Universe()
    uni.save()

    u1 = User.load(username="admin")
    u1.password = app.config["test_password"]
    u1.role = Role.FULL_ADMIN
    assert u1.save()

    # teardown called after all tests in session have completed
    def teardown(): pass
    request.addfinalizer(teardown)

    logger.debug("(users) module level app setup completed")
    return app

@pytest.fixture(scope="function")
def userprep(request, app):
    # perform proper proper user prep/cleanup
    # at this point, only requirement is to delete all users except local and admin
   
    logger.debug("%s test setup", "*"*80)

    # for settings to default values
    Settings.delete(_filters={})
    s = Settings()
    assert s.save()

    # set client to authenticated user before starting any tests
    app.client = app.test_client()
    response = app.client.post(login_url, data=json.dumps({
        "username": "admin",
        "password": app.config["test_password"]
    }), content_type="application/json")
    assert response.status_code == 200

    def teardown():
        logger.debug("%s test teardown", "-"*80)
        User.delete(_filters={"$and":[{"username":{"$ne":"admin"}}, {"username":{"$ne":"local"}}]})
        Session.delete(_filters={})
    request.addfinalizer(teardown)
    logger.debug("********** test start")
    return

def get_cookies(test_client):
    # return dict of cookies indexed by cookie name for a flask test_client object
    ret = {}
    try:
        for cookie in test_client.cookie_jar: ret[cookie.name] = cookie
    except Exception as e:
        logger.warn("failed to extract cookies from test_client: %s", e)
    return ret

def create_test_user(username="test_user", **kwargs):
    # create and return test user with provided username
    u = User.load(username=username, **kwargs)
    assert u.save()
    return u

def test_api_logout_user_with_post(app, userprep):
    # login and logout via post and verify unauthorized on read
    # test old cookie andensure session is still blocked
    c = app.test_client()

    response = c.post(login_url, data=json.dumps({
        "username": "admin",
        "password": app.config["test_password"]
    }), content_type="application/json")
    assert response.status_code == 200
    # save session cookie for future call
    old_cookie = get_cookies(c)["session"]

    # user read should be fine
    response = c.get("/api/user")
    assert response.status_code == 200

    # logout user via post method
    response = c.post(logout_url)
    assert response.status_code == 200

    # manually set old, invalid session cookie to send on next call
    logger.debug("%s, %s, %s", old_cookie.domain, old_cookie.name, old_cookie.value)
    c.set_cookie(old_cookie.domain, old_cookie.name, old_cookie.value)

    # user should not be unauthenticated
    response = c.get("/api/user")
    assert response.status_code == 401 

def test_api_session_timeout(app, userprep):
    # force settings timeout to 0.1 second and ensure session timeout works
    s = Settings.load(session_timeout=0.1)
    assert s.save(skip_validation=True)

    c = app.test_client()
    response = c.post(login_url, data=json.dumps({
        "username": "admin",
        "password": app.config["test_password"]
    }), content_type="application/json")
    assert response.status_code == 200

    time.sleep(0.2)

    response = c.get("/api/user")
    assert response.status_code == 401 

def test_api_session_csfr_token(app, userprep):
    # enable csfr token and ensure valid session without token is blocked

    c = app.test_client()
    response = c.post(login_url, data=json.dumps({
        "username": "admin",
        "password": app.config["test_password"],
        "token_required": True,
    }), content_type="application/json")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "token" in js
    assert "session" in js

    logger.debug("ensure 401 returned when token not sent")
    response = c.get("/api/user")
    assert response.status_code == 401 

    # ensure token present in url is accepted
    # response = c.get("/api/user?app-token=%s" % js["token"])
    # assert response.status_code == 200

    # ensure token present in data is accepted
    # response = c.get("/api/user", data=json.dumps({
    #    "app-token": js["token"]
    # }), content_type="application/json")
    # assert response.status_code == 200

    # ensure token present in header is accepted with session in cookie
    logger.debug("ensure success with token in headers and session in cookie")
    response = c.get("/api/user", headers={
        "app-token": js["token"],
    })
    assert response.status_code == 200

    # ensure token present in header with session in header (no cookie) is accepted
    logger.debug("ensure success with token in headers and session in headers (no cookie)")
    c2 = app.test_client()
    response = c2.get("/api/user", headers={
        "app-token": js["token"],
        "session": js["session"],
    })
    assert response.status_code == 200

    # ensure an invalid sesison/token is not accepted
    logger.debug("ensure 401 with bad token and valid session")
    response = c.get("/api/user", headers={
        "app-token": "bad_token1",
        "session": js["session"],
    })
    assert response.status_code == 401

    # ensure an invalid sesison/token is not accepted
    logger.debug("ensure 401 with valid token and bad session")
    response = c.get("/api/user", headers={
        "app-token": js["token"],
        "session": "bad_session",
    })
    assert response.status_code == 401

def test_api_create_user_incomplete_data(app, userprep):
    # create a user with no data
    response = app.client.post("/api/user", data=json.dumps({}), 
        content_type='application/json')
    assert response.status_code == 400  # invalid data

    # create a user with username missing
    response = app.client.post("/api/user", data=json.dumps({ 
        "password": "pass12345"    
    }), content_type='application/json')
    assert response.status_code == 400  # invalid data

    # create a user with password missing - accept it
    response = app.client.post("/api/user", data=json.dumps({ 
        "username": "bad_user"
    }), content_type='application/json')
    assert response.status_code == 200

def test_api_create_user_invalid_data(app, userprep):
    # create a user with invalid role and expect 400 - invalid data
    response = app.client.post("/api/user", data=json.dumps({
        "username": "bad_user",
        "password": "P1234cdef",
        "role": 233321939929193
    }), content_type="application/json")
    assert response.status_code == 400

def test_api_create_user_block_duplicate(app, userprep):
    # block attempts at creating duplicate username
    response = app.client.get("/api/uni/username-admin")
    assert response.status_code == 200

    response = app.client.post("/api/user", data=json.dumps({
        "username": "admin",
        "password": "P1234cdef",
        "role": Role.FULL_ADMIN
    }), content_type="application/json")
    assert response.status_code == 400

def test_api_create_user_block_root(app, userprep):
    # block attempts to create username 'root'
    response = app.client.post("/api/user", data=json.dumps({
        "username": "root",
        "password": "P1234cdef",
        "role": Role.FULL_ADMIN
    }), content_type="application/json")
    assert response.status_code == 400

def test_api_create_user_success(app, userprep):
    # create user and verify user is created
    response = app.client.post("/api/user", data=json.dumps({
        "username": "good_user",
        "password": "P1234cdef",
        "role": Role.USER,
    }), content_type='application/json')
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "success" in js and js["success"]

    # read user - verify user is created
    response = app.client.get(keyed_url.format("good_user"))
    assert response.status_code == 200
    js = json.loads(response.data)
    js = js["objects"][0]["user"]
    assert js["username"] == "good_user"

def test_api_update_user_success(app, userprep):
    # update user and verify update is successful
   
    # create a test user first
    create_test_user(username="test_user")
    response = app.client.patch(keyed_url.format("test_user"), data=json.dumps({
        "role": Role.BLACKLIST
    }), content_type="application/json")
    assert response.status_code == 200

    # read user - verify role is updated
    response = app.client.get(keyed_url.format("test_user"))
    js = json.loads(response.data)
    js = js["objects"][0]["user"]
    assert js["role"] == Role.BLACKLIST

def test_api_delete_user_success(app, userprep):
    # delete user and verify user is not longer present
    
    # create a test user first
    create_test_user(username="test_user")
    response = app.client.delete(keyed_url.format("test_user"))
    assert response.status_code == 200
    
    # verify user is deleted
    response = app.client.get(keyed_url.format("test_user"))
    assert response.status_code == 404
    
def test_api_read_user_unknown(app, userprep):
    # verify that a read to unknown user returns 404 - not found
    response = app.client.get(keyed_url.format("uknown_user_123456"))
    assert response.status_code == 404

def test_api_read_user_password_not_returned(app, userprep):
    # read a user and verify 'password' field is not returned
    response = app.client.get(keyed_url.format("admin"))
    js = json.loads(response.data)
    js = js["objects"][0]
    assert "password" not in js

def test_api_read_user_all(app, userprep):
    # read all users and verify non-empty list is received
    response = app.client.get("/api/user")
    js = json.loads(response.data)
    assert "objects" in js
    assert type(js["objects"]) is list and len(js["objects"])>0

def test_api_read_user_non_admin(app, userprep):
    # for a non-admin user, perform bulk read and ensure ensure only local username is returned
    # for reads to other users, block it

    # create a non-admin user
    create_test_user(username="test_user", password="password")

    # login with original user password
    c = app.test_client()
    response = c.post(login_url, data=json.dumps({
        "username": "test_user",
        "password": "password",
    }), content_type="application/json")
    assert response.status_code == 200
        
    response = c.get("/api/user")
    assert response.status_code == 200
    js = json.loads(response.data)
    logger.debug(pretty_print(js))
    assert js["count"] == 1
    assert js["objects"][0]["user"]["username"] == "test_user"

    response = c.get(keyed_url.format("admin"))
    assert response.status_code == 403

def test_api_update_user_username_not_allowed(app, userprep):
    # verify that update attempt to username attribute is blocked

    # create a test user first
    create_test_user(username="test_user")
    response = app.client.patch(keyed_url.format("test_user"), data=json.dumps({
        "username":"not_test_user"
    }), content_type='application/json')
    assert response.status_code == 400

def test_api_update_user_unknown_field(app, userprep):
    # verify that update with no valid fields is blocked
    
    # create a test user first
    create_test_user(username="test_user")
    response = app.client.patch(keyed_url.format("test_user"), data=json.dumps({
        "invalid_username_field": "some_value"
    }), content_type='application/json')
    assert response.status_code == 400

def test_api_update_user_invalid_data(app, userprep):
    # update user with invalid role and expect 400 - invalid data

    # create a test user first
    create_test_user(username="test_user")
    response = app.client.patch(keyed_url.format("test_user"), data=json.dumps({
        "role": 12345929293922
    }), content_type='application/json')
    assert response.status_code == 400

def test_api_delete_user_unknown(app, userprep):
    # delete an unknown error returns 404 - not found
    response = app.client.delete(keyed_url.format("unknown_randmon_user_12345"))
    assert response.status_code == 404

def test_api_user_pwreset_success(app, userprep):
    # create a user and reset user password. validate we can access API with new password

    # create a test user first
    create_test_user(username="test_user", password="password")

    # login with original user password
    c = app.test_client()
    response = c.post(login_url, data=json.dumps({
        "username": "test_user",
        "password": "password",
    }), content_type="application/json")
    assert response.status_code == 200

    # get password reset key
    response = c.get(keyed_pwreset_url.format("test_user"))
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "key" in js

    # perform non-authenticated password reset with correct reset key
    c2 = app.test_client()
    response = c2.post(pwreset_url, data=json.dumps({
        "username": "test_user",
        "password": "new-password",
        "password_reset_key": js["key"]
    }), content_type="application/json")
    assert response.status_code == 200

    # login with old password and ensure it fails
    response = c.post(login_url, data=json.dumps({
        "username": "test_user",
        "password": "password",
    }), content_type="application/json")
    assert response.status_code == 401

    # login with new password and ensure it succeeds
    response = c.post(login_url, data=json.dumps({
        "username": "test_user",
        "password": "new-password",
    }), content_type="application/json")
    assert response.status_code == 200

def test_api_user_pwreset_block_non_admin(app, userprep):
    # prevent a non-admin user from issuing password reset for another user

    # create a test user first
    create_test_user(username="test_user1", password="password1")
    create_test_user(username="test_user2", password="password2")

    # login as test_user1
    c = app.test_client()
    response = c.post(login_url, data=json.dumps({
        "username": "test_user1",
        "password": "password1",
    }), content_type="application/json")
    assert response.status_code == 200

    # test_user1 get password reset key for test_user2 (should be blocked)
    response = c.get(keyed_pwreset_url.format("test_user2"))
    assert response.status_code == 403

def test_api_user_pwreset_invalid_key_admin_user(app, userprep):
    # ensure that password resets without a key fail for admin
    #
    # create a test user first
    create_test_user(username="test_user", password="password")

    # with admin account, get password reset key
    response = app.client.get(keyed_pwreset_url.format("test_user"))
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "key" in js

    # perform password reset as admin without key
    response = app.client.post(pwreset_url, data=json.dumps({
        "username": "test_user",
        "password": "new-password",
    }), content_type="application/json")
    assert response.status_code == 400

    # perform password reset as admin with invalid key
    response = app.client.post(pwreset_url, data=json.dumps({
        "username": "test_user",
        "password": "new-password",
        "password_reset_key": "invalid_key_123",
    }), content_type="application/json")
    assert response.status_code == 400

    # try to login as user with new password (should fail since pwreset failed)
    c = app.test_client()
    response = c.post(login_url, data=json.dumps({
        "username": "test_user",
        "password": "new-password",
    }), content_type="application/json")
    assert response.status_code == 401

    # try to login as user with old password (should succeed)
    response = c.post(login_url, data=json.dumps({
        "username": "test_user",
        "password": "password",
    }), content_type="application/json")
    assert response.status_code == 200

