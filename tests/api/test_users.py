import json
from app.models.roles import Roles

"""
Users database data available (and possibly manipulated) by/for users tests:
    tests/testdata/users.json

"""

def test_api_logout_user_with_post(app):
    # login and logout via post and verify unauthorized on read
    c = app.test_client()
    response = c.post("/api/login", data=json.dumps({
        "username": "admin",
        "password": app.config["test_password"]
    }), content_type="application/json")
    assert response.status_code == 200

    # logout user via post method
    response = c.post("/api/logout")
    assert response.status_code == 200

    # user should not be unauthenticated
    response = c.get("/api/users")
    assert response.status_code == 401 

def test_api_logout_user_with_get(app):
    # login and logout via post and verify unauthorized on read
    c = app.test_client()
    response = c.post("/api/login", data=json.dumps({
        "username": "admin",
        "password": app.config["test_password"]
    }), content_type="application/json")
    assert response.status_code == 200

    # logout user via post method
    response = c.get("/api/logout")
    assert response.status_code == 200

    # user should not be unauthenticated
    response = c.get("/api/users")
    assert response.status_code == 401 

def test_api_create_user_incomplete_data(app):
    # create a user with no data
    response = app.client.post("/api/users", data=json.dumps({}), 
        content_type='application/json')
    assert response.status_code == 400  # invalid data

    # create a user with username missing
    response = app.client.post("/api/users", data=json.dumps({ 
        "password": "pass12345"    
    }), content_type='application/json')
    assert response.status_code == 400  # invalid data

    # create a user with password missing
    response = app.client.post("/api/users", data=json.dumps({ 
        "username": "bad_user"
    }), content_type='application/json')
    assert response.status_code == 400  # invalid data

def test_api_create_user_invalid_data(app):
    # create a user with invalid role and expect 400 - invalid data
    response = app.client.post("/api/users", data=json.dumps({
        "username": "bad_user",
        "password": "P1234cdef",
        "role": 233321939929193
    }), content_type="application/json")
    assert response.status_code == 400

def test_api_create_user_block_duplicate(app):
    # block attempts at creating duplicate username
    response = app.client.post("/api/users", data=json.dumps({
        "username": "admin",
        "password": "P1234cdef",
        "role": Roles.FULL_ADMIN
    }), content_type="application/json")
    assert response.status_code == 400

def test_api_create_user_block_root(app):
    # block attempts to create username 'root'
    response = app.client.post("/api/users", data=json.dumps({
        "username": "root",
        "password": "P1234cdef",
        "role": Roles.FULL_ADMIN
    }), content_type="application/json")
    assert response.status_code == 400

def test_api_create_user_success(app):
    # create user and verify user is created
    response = app.client.post("/api/users", data=json.dumps({
        "username": "good_user",
        "password": "P1234cdef",
        "role": Roles.USER,
    }), content_type='application/json')
    assert response.status_code == 200

    # read user - verify user is created using location in reply
    js = json.loads(response.data)
    assert "location" in js
    assert "success" in js and js["success"]

    response = app.client.get(js["location"])
    assert response.status_code == 200
    js = json.loads(response.data)
    assert js["username"] == "good_user"

def test_api_update_user_success(app):
    # update user and verify update is successful
    response = app.client.post("/api/users/G_user1", data=json.dumps({
        "role": Roles.BLACKLIST
    }), content_type="application/json")
    assert response.status_code == 200

    # read user - verify role is updated
    response = app.client.get("/api/users/G_user1")
    js = json.loads(response.data)
    assert js["role"] == Roles.BLACKLIST

def test_api_delete_user_success(app):
    # delete user and verify user is not longer present
    response = app.client.delete("/api/users/delete_user")
    assert response.status_code == 200
    
    # verify user is deleted
    response = app.client.get("/api/users/delete_user")
    assert response.status_code == 404
    
def test_api_read_user_unknown(app):
    # verify that a read to unknown user returns 404 - not found
    response = app.client.get("/api/users/unknown_randmon_user_12345")
    assert response.status_code == 404

def test_api_read_user_password_not_returned(app):
    # read a user and verify 'password' field is not returned
    response = app.client.get("/api/users/G_user1")
    js = json.loads(response.data)
    assert "password" not in js

def test_api_read_user_all(app):
    # read all users and verify non-empty list is received
    response = app.client.get("/api/users")
    js = json.loads(response.data)
    assert "users" in js
    assert type(js["users"]) is list and len(js["users"])>0

def test_api_update_user_username_not_allowed(app):
    # verify that update attempt to username is blocked
    response = app.client.post("/api/users/G_user1", data=json.dumps({
        "username":"not_user1"
    }), content_type='application/json')
    assert response.status_code == 400

def test_api_update_user_unknown_field(app):
    # verify that update with no valid fields is blocked
    response = app.client.post("/api/users/G_user1", data=json.dumps({
        "invalid_username_field": "some_value"
    }), content_type='application/json')
    assert response.status_code == 400

def test_api_update_user_invalid_data(app):
    # update user with invalid role and expect 400 - invalid data
    response = app.client.post("/api/users/G_user1", data=json.dumps({
        "role": 12345929293922
    }), content_type='application/json')
    assert response.status_code == 400

def test_api_delete_user_unknown(app):
    # delete an unknown error returns 404 - not found
    response = app.client.delete("/api/users/unknown_randmon_user_12345")
    assert response.status_code == 404

def test_api_user_pwreset_success(app):
    # create a user and reset user password. validate we can access API with
    # new password

    # create user first
    response = app.client.post("/api/users", data=json.dumps({
        "username": "T_user1",
        "password": "P1234cdef",
        "role": Roles.USER,
    }), content_type='application/json')
    assert response.status_code == 200

    # login with original user password
    c = app.test_client()
    response = c.post("/api/login", data=json.dumps({
        "username": "T_user1",
        "password": "P1234cdef",
    }), content_type="application/json")
    assert response.status_code == 200

    # get password reset key
    response = c.get("/api/users/T_user1/pwreset")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "url" in js
    assert "key" in js

    # perform non-authenticated password reset
    c2 = app.test_client()
    response = c2.post("/api/users/pwreset", data=json.dumps({
        "username": "T_user1",
        "password": "fedc4321P",
        "key": js["key"]
    }), content_type="application/json")
    assert response.status_code == 200

    # login with old password and ensure it fails
    response = c.post("/api/login", data=json.dumps({
        "username": "T_user1",
        "password": "P1234cdef",
    }), content_type="application/json")
    assert response.status_code == 401

    # login with new password and ensure it succeeds
    response = c.post("/api/login", data=json.dumps({
        "username": "T_user1",
        "password": "fedc4321P",
    }), content_type="application/json")
    assert response.status_code == 200

    # delete user
    response = app.client.delete("/api/users/T_user1")
    assert response.status_code == 200

def test_api_user_pwreset_block_non_admin(app):
    # prevent a non-admin user from issuing password reset for another user

    # create temporary users first
    response = app.client.post("/api/users", data=json.dumps({
        "username": "T_user2",
        "password": "P1234cdef2",
        "role": Roles.USER,
    }), content_type='application/json')
    assert response.status_code == 200

    response = app.client.post("/api/users", data=json.dumps({
        "username": "T_user3",
        "password": "P1234cdef3",
        "role": Roles.USER,
    }), content_type='application/json')
    assert response.status_code == 200

    # login as T_user3
    c = app.test_client()
    response = c.post("/api/login", data=json.dumps({
        "username": "T_user3",
        "password": "P1234cdef3",
    }), content_type="application/json")
    assert response.status_code == 200

    # get password reset key (should be blocked)
    response = c.get("/api/users/T_user2/pwreset")
    assert response.status_code == 403

    # delete T_user2 and T_user3
    response = app.client.delete("/api/users/T_user2")
    assert response.status_code == 200

    response = app.client.delete("/api/users/T_user3")
    assert response.status_code == 200

def test_api_user_pwreset_invalid_key_admin_user(app):
    # ensure that password resets without a key fail for admin

    # create temporary users first
    response = app.client.post("/api/users", data=json.dumps({
        "username": "T_user4",
        "password": "P1234cdef",
        "role": Roles.USER,
    }), content_type='application/json')
    assert response.status_code == 200

    # get password reset key
    response = app.client.get("/api/users/T_user4/pwreset")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "url" in js
    assert "key" in js

    # perform password reset as admin without key
    response = app.client.post("/api/users/pwreset", data=json.dumps({
        "username": "T_user4",
        "password": "new-password-1234",
    }), content_type="application/json")
    assert response.status_code == 400

    # perform password reset as admin with invalid key
    response = app.client.post("/api/users/pwreset", data=json.dumps({
        "username": "T_user4",
        "password": "new-password-1234",
        "key": "invalid_key_123",
    }), content_type="application/json")
    assert response.status_code == 400

    # try to login as user with new password (should fail since pwreset failed)
    c = app.test_client()
    response = c.post("/api/login", data=json.dumps({
        "username": "T_user4",
        "password": "new-password-1234",
    }), content_type="application/json")
    assert response.status_code == 401

    # try to login as user with old password (should succeed)
    response = c.post("/api/login", data=json.dumps({
        "username": "T_user4",
        "password": "P1234cdef",
    }), content_type="application/json")
    assert response.status_code == 200

    # delete user
    response = app.client.delete("/api/users/T_user4")
    assert response.status_code == 200

def test_api_user_pwreset_invalid_key_normal_user(app):
    # ensure that password resets without a key fail for normal users

    # create temporary users first
    response = app.client.post("/api/users", data=json.dumps({
        "username": "T_user5",
        "password": "P1234cdef",
        "role": Roles.USER,
    }), content_type='application/json')
    assert response.status_code == 200

    # login as new non-admin user
    c = app.test_client()
    response = c.post("/api/login", data=json.dumps({
        "username": "T_user5",
        "password": "P1234cdef",
    }), content_type="application/json")
    assert response.status_code == 200

    # get password reset key this time, just try to reset password
    # perform password reset as normal user without key
    response = c.post("/api/users/pwreset", data=json.dumps({
        "username": "T_user5",
        "password": "new-password-1234",
    }), content_type="application/json")
    assert response.status_code == 400

    # perform password reset as admin with invalid key
    response = c.post("/api/users/pwreset", data=json.dumps({
        "username": "T_user5",
        "password": "new-password-1234",
        "key": "invalid_key_123",
    }), content_type="application/json")
    assert response.status_code == 400

    # try to login as user with new password (should fail since pwreset failed)
    c2 = app.test_client()
    response = c2.post("/api/login", data=json.dumps({
        "username": "T_user5",
        "password": "new-password-1234",
    }), content_type="application/json")
    assert response.status_code == 401

    # try to login as user with old password (should succeed)
    response = c2.post("/api/login", data=json.dumps({
        "username": "T_user5",
        "password": "P1234cdef",
    }), content_type="application/json")
    assert response.status_code == 200

    # delete user
    response = app.client.delete("/api/users/T_user5")
    assert response.status_code == 200
