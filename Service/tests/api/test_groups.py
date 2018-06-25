import json

"""
Users database data available (and possibly manipulated) by/for users tests:
    tests/testdata/users.json
Groups database data available
    tests/testdata/groups.json

"""

def test_api_groups_create_group(app):
    # create a group and read it to ensure it was successfully created
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group0",
        "members": ["F_user2"]
    }), content_type='application/json')
    assert response.status_code == 200

    # get location of new resource (expected in create)
    js = json.loads(response.data)
    assert "location" in js
    
    # read created resource and ensure values are set
    response = app.client.get(js["location"])
    assert response.status_code == 200
    js = json.loads(response.data)
    # ensure all attributes are present
    assert "group" in js        
    assert "members" in js
    # ensure attributes are correct value
    assert js["group"] == "T_group0"
    assert js["members"] == ["F_user2"]

    # read groups list from users and ensure F_user2 has group G_group1
    response = app.client.get("/api/users/F_user2")
    assert response.status_code == 200      # invalid test data...
    js = json.loads(response.data)
    assert "groups" in js
    assert "T_group0" in js["groups"]

def test_api_groups_create_duplicate_group(app):
    # create a duplicate group name and ensure it fails (F_group1 to 8 exists)
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "F_group1",
        "members": []
    }), content_type='application/json')
    assert response.status_code == 400

def test_api_groups_read_groups(app):
    # read all existing groups from database and ensure attributes on each:
    # (group, members)
    # F_group1 to 8 exists
    response = app.client.get("/api/groups")
    assert response.status_code == 200

    js = json.loads(response.data)
    assert "groups" in js
    assert len(js["groups"])>1
    for g in js["groups"]:
        assert "group" in g
        assert "members" in g

def test_api_groups_read_group(app):
    # read single group from database and ensure attributes: 
    # (group, members)
    response = app.client.get("/api/groups/F_group1")
    assert response.status_code == 200

    js = json.loads(response.data)
    assert "group" in js
    assert "members" in js
    assert js["group"] == "F_group1"

def test_api_groups_update_name_fail(app):
    # ensure update to group name fails (F_group1)
    response = app.client.post("/api/groups/F_group1", data=json.dumps({
        "group": "T_group0"
    }), content_type='application/json')

    # read group and check name
    response = app.client.get("/api/groups/F_group1")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "group" in js
    assert js["group"] == "F_group1"

def test_api_groups_update_group_unknown(app):
    # post update to unknown group and ensure it fails
    response = app.client.post("/api/groups/uknown_group1", data=json.dumps({
        "members": ["F_user1"]
    }), content_type='application/json')
    assert response.status_code == 404

def test_api_groups_update_group(app):
    # overwrite existing 'member's attributes with new members list
    # ensure new users are present in members list and has group added to 
    # user's group list

    # create a new group first
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group1",
        "members": ["F_user1"]
    }), content_type='application/json')
    assert response.status_code == 200

    # ensure group is originally added to user
    response = app.client.get("/api/users/F_user1")
    assert response.status_code == 200  # invalid test data set...
    js = json.loads(response.data)
    assert "T_group1" in js["groups"]   # 'members' overwritten

    # overwrite members attributes with F_user2
    response = app.client.post("/api/groups/T_group1", data=json.dumps({
        "members": ["F_user2"]
    }), content_type='application/json')
    assert response.status_code == 200

    # read 'members' from group and 'groups' from user to ensure that
    # both are updated
    response = app.client.get("/api/groups/T_group1")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert js["members"] == ["F_user2"]

    # ensure group is removed from F_user1
    response = app.client.get("/api/users/F_user1")
    assert response.status_code == 200  
    js = json.loads(response.data)
    assert "T_group1" not in js["groups"]

    # ensure group is added to F_user2
    response = app.client.get("/api/users/F_user2")
    assert response.status_code == 200  
    js = json.loads(response.data)
    assert "T_group1" in js["groups"]

    # delete test group
    response = app.client.delete("/api/groups/T_group1")
    assert response.status_code == 200

def test_api_groups_update_group_add_incr(app):
    # add single member to group using incr api
    # ensure new user is present in members list and has group added to 
    # user's group list

    # create a new group first
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group2",
        "members": ["F_user1"]
    }), content_type='application/json')
    assert response.status_code == 200

    response = app.client.post("/api/groups/incr", data=json.dumps({
        "group": "T_group2",
        "members": {"add": ["F_user2"]}
    }), content_type='application/json')
    assert response.status_code == 200

    # read 'members' from group and 'groups' from user to ensure that
    # both are updated
    response = app.client.get("/api/groups/T_group2")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "F_user2" in js["members"]   # 'members' appended 

    response = app.client.get("/api/users/F_user2")
    assert response.status_code == 200  # invalid test data set...
    js = json.loads(response.data)
    assert "T_group2" in js["groups"]

    # delete test group
    response = app.client.delete("/api/groups/T_group2")
    assert response.status_code == 200

def test_api_groups_update_group_remove_incr(app):
    # remove single member to group using incr api
    # ensure user is not present in members list and has group removed from 
    # user's group list

    # create a new group first
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group3",
        "members": ["F_user1", "F_user2"],
    }), content_type='application/json')
    assert response.status_code == 200

    # update members attribute
    response = app.client.post("/api/groups/incr", data=json.dumps({
        "group": "T_group3",
        "members": {"remove": ["F_user2"]}
    }), content_type='application/json')
    assert response.status_code == 200

    # read 'members' from group and 'groups' from user to ensure that
    # both are updated
    response = app.client.get("/api/groups/T_group3")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "F_user2" not in js["members"]   # 'members' updated

    response = app.client.get("/api/users/F_user2")
    assert response.status_code == 200  
    js = json.loads(response.data)
    assert "T_group3" not in js["groups"]

    # delete test group
    response = app.client.delete("/api/groups/T_group3")
    assert response.status_code == 200

def test_api_groups_delete_group_unknown(app):
    # ensure delete operation to unknown group fails
    response = app.client.delete("/api/groups/unknown_group")
    assert response.status_code == 404

def test_api_groups_delete_group(app):
    # ensure delete group operation removes the group and group from each
    # user in members list

    # create a group and read it to ensure it was successfully created
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group4",
        "members": ["F_user2"]
    }), content_type='application/json')
    assert response.status_code == 200

    # read user and ensure group was added to the user
    response = app.client.get("/api/users/F_user2")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "T_group4" in js["groups"]

    # ensure group exists
    response = app.client.get("/api/groups/T_group4")
    assert response.status_code == 200

    # delete group
    response = app.client.delete("/api/groups/T_group4")
    assert response.status_code == 200

    # read group which should no longer exist
    response = app.client.get("/api/groups/T_group4")
    assert response.status_code == 404

    # read user and ensure group is removed from the user
    response = app.client.get("/api/users/F_user2")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "T_group4" not in js["groups"]

def test_api_groups_add_group_before_user(app):
    # add a user to a group before the user is created.  Then create the user
    # and ensure user has group as part of it's 'groups' attribute
    
    # create temporary group first with user
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group101",
        "members": ["T_user101"]
    }), content_type='application/json')
    assert response.status_code == 200

    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group102",
        "members": ["T_user101"]
    }), content_type='application/json')
    assert response.status_code == 200

    # create temporary user 
    response = app.client.post("/api/users", data=json.dumps({
        "username": "T_user101",
        "password": "P1234cdef",
    }), content_type='application/json')
    assert response.status_code == 200

    # read user and ensure group is present
    js = json.loads(response.data)
    assert "location" in js
    response = app.client.get(js["location"])
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "groups" in js and "T_group101" in js["groups"]
    assert "groups" in js and "T_group102" in js["groups"]

    # delete user and group
    response = app.client.delete("/api/users/T_user101")
    assert response.status_code == 200
    response = app.client.delete("/api/groups/T_group101")
    assert response.status_code == 200
    response = app.client.delete("/api/groups/T_group102")
    assert response.status_code == 200

def test_api_groups_delete_user_maintain_groups(app):
    # delete a user and ensure user is NOT removed as member from groups

    # create a few groups
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group5",
        "members": ["F_user1", "F_user2", "F_user3", "T_user5"]
    }), content_type='application/json')
    assert response.status_code == 200

    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group6",
        "members": ["F_user1", "F_user2", "F_user3", "T_user5"]
    }), content_type='application/json')
    assert response.status_code == 200

    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group7",
        "members": ["F_user1", "F_user2", "F_user3", "T_user5"]
    }), content_type='application/json')
    assert response.status_code == 200

    # create a user 
    response = app.client.post("/api/users", data=json.dumps({
        "username": "T_user5",
        "password": "P1234cdef",
    }), content_type='application/json')
    assert response.status_code == 200

    # delete user
    response = app.client.delete("/api/users/T_user5")
    assert response.status_code == 200

    # check that user is still a member of previous groups
    response = app.client.get("/api/groups/T_group5")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "T_user5" in js["members"]
    response = app.client.get("/api/groups/T_group6")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "T_user5" in js["members"]
    response = app.client.get("/api/groups/T_group7")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "T_user5" in js["members"]

    # delete temp groups
    response = app.client.delete("/api/groups/T_group5")
    assert response.status_code == 200
    response = app.client.delete("/api/groups/T_group6")
    assert response.status_code == 200
    response = app.client.delete("/api/groups/T_group7")
    assert response.status_code == 200

def test_api_groups_delete_user_delete_groups(app):
    # delete a user and ensure user is removed as member from groups

    # create a few groups
    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group5",
        "members": ["F_user1", "F_user2", "F_user3", "T_user5"]
    }), content_type='application/json')
    assert response.status_code == 200

    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group6",
        "members": ["F_user1", "F_user2", "F_user3", "T_user5"]
    }), content_type='application/json')
    assert response.status_code == 200

    response = app.client.post("/api/groups", data=json.dumps({
        "group": "T_group7",
        "members": ["F_user1", "F_user2", "F_user3", "T_user5"]
    }), content_type='application/json')
    assert response.status_code == 200

    # create a user 
    response = app.client.post("/api/users", data=json.dumps({
        "username": "T_user5",
        "password": "P1234cdef",
    }), content_type='application/json')
    assert response.status_code == 200

    # delete user
    response = app.client.delete("/api/users/T_user5", data=json.dumps({
        "sync_groups": True
    }), content_type="application/json")
    assert response.status_code == 200

    # check that user is still a member of previous groups
    response = app.client.get("/api/groups/T_group5")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "T_user5" not in js["members"]
    response = app.client.get("/api/groups/T_group6")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "T_user5" not in js["members"]
    response = app.client.get("/api/groups/T_group7")
    assert response.status_code == 200
    js = json.loads(response.data)
    assert "T_user5" not in js["members"]

    # delete temp groups
    response = app.client.delete("/api/groups/T_group5")
    assert response.status_code == 200
    response = app.client.delete("/api/groups/T_group6")
    assert response.status_code == 200
    response = app.client.delete("/api/groups/T_group7")
    assert response.status_code == 200

