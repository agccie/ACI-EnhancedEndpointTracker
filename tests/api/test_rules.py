import json

"""
Test Rule data ('F' implies fixed (read-only) will not be changed by
any test)

/F_rule1
    owner: F_user1
    inherit_read: True
    inherit_write: True
    read_users:  
    read_groups: F_group2    (contains F_user2)
    write_users:
    write_groups: F_group4   (contains F_user4)

/F_rule1/sub2 (non-existing)

/F_rule1/sub2/sub3
    owner: F_user3
    inherit_read: True
    inherit_write: False
    read_users:  F_user5
    write_users: F_user5
    read_groups: F_group6    (contains F_user6)
    write_groups: F_group7   (contains F_user7)

Expected results ('admin' can read/write any rule...)
    /F_rule1
        read: F_user1 (owner), F_user2 (group2), F_user4 (write=read) 
        write: F_user1 (owner), F_user4 (group4), 
        * no read - F_user3, F_user5, F_user6, F_user7
        * no write - F_user2, F_user3, F_user5, F_user6, F_user7

    /F_rule1/sub2  (inherits from /F_rule1)
        ..

    /F_rule1/sub2/sub3
        read: F_user3(owner), F_user5, F_user6, F_user7(write=read),
              F_user1(p-owner), F_user2(p-read), F_user4(p-write=read)
        write: F_user3(owner), F_user5, F_user7
        * no read -  no one...
        * no write - F_user1, F_user2, F_user4, F_user6
"""

def test_api_create_rule_success(app):
    # user can create a rule with specific dn
    response = app.client.post("/api/rules", data=json.dumps({
        "dn": "/G_rule1",
        "inherit_read": False,
        "inherit_write": False,
        "read_users": ["F_user1"],
        "write_users": ["F_user2"],
        "read_groups": ["F_group1"],
        "write_groups": ["F_group2"]
    }), content_type='application/json')
    assert response.status_code == 200   

    # get location of new resource (expected in create)
    js = json.loads(response.data)
    assert "location" in js
    
    # read created resource and ensure values are set
    response = app.client.get(js["location"])
    assert response.status_code == 200
    js = json.loads(response.data)
    assert js["dn"] == "/G_rule1"
    assert js["inherit_read"] is False
    assert js["inherit_write"] is False
    assert js["read_users"] == ["F_user1"]
    assert js["write_users"] == ["F_user2"]
    assert js["read_groups"] == ["F_group1"]
    assert js["write_groups"] == ["F_group2"]

def test_api_create_rule_block_duplicate(app):
    # no user can create a rule with duplicate dn to existing rule
    response = app.client.post("/api/rules", data=json.dumps({
        "dn": "/F_rule1",
        "inherit_read": False,
    }), content_type='application/json')
    assert response.status_code == 400

def test_api_create_rule_allow_sub_domain_with_write_access(app):
    # allow a user with write access to dn to create sub-dn rules
    pass

def test_api_create_rule_allow_sub_domain_owner(app):
    # allow owner to create a rule as sub-domain of existing rule
    pass

def test_api_create_rule_block_sub_domain_without_write_access(app):
    # prevent user from creating a rule with dn that is a sub dn that 
    # they dont have access to with inherit set
    pass

def test_api_create_rule_allow_sub_domain_no_inherit(app):
    # for a rule that has inherit set to false, a non-write access user
    # to upper dn has write access to a sub-dn
    pass

def test_api_read_rule_owner_success(app):
    # ensure rule owner can read rule
    pass

def test_api_read_rule_non_owner_success(app):
    # ensure non-owner with read access can read rule (+group)
    pass

def test_api_read_rule_admin_success(app):
    # ensure admin can read rule even if not a member
    pass

def test_api_read_rule_block(app):
    # ensure users that do not have read access to rule cannot read it
    pass

def test_api_update_rule_owner_success(app):
    # ensure owner has update access to a rule 
    pass

def test_api_update_rule_non_owner_success(app):
    # ensure non-owner user with write access can update a rule (+group)
    pass

def test_api_update_rule_admin_success(app):
    # ensure admin can update rule even if not a member
    pass

def test_api_update_rule_block(app):
    # ensure users that do not have write access to group cannot update it
    pass

def test_api_update_rule_change_owner_by_admin_success(app):
    # ensure that admin can change current owner of rule
    pass

def test_api_update_rule_change_owner_by_owner_success(app):
    # ensure that rule owner can change current owner of rule
    pass

def test_api_update_rule_change_owner_block(app):
    # only admin/owner are allowed to change rule owner, ensure that other
    # users with write access to rule cannot update rule owner.
    pass

""" test incremental updates to rule
def test_api_update_rule_incr_add_read_user(app):
def test_api_update_rule_incr_add_read_users(app):
def test_api_update_rule_incr_add_write_user(app):
def test_api_update_rule_incr_add_write_users(app):
def test_api_update_rule_incr_add_read_group(app):
def test_api_update_rule_incr_add_read_groups(app):
def test_api_update_rule_incr_add_write_group(app):
def test_api_update_rule_incr_add_write_groups(app):
def test_api_update_rule_incr_remove_read_user(app):
def test_api_update_rule_incr_remove_read_users(app):
def test_api_update_rule_incr_remove_read_group(app):
def test_api_update_rule_incr_remove_read_groups(app):
def test_api_update_rule_incr_remove_write_user(app):
def test_api_update_rule_incr_remove_write_users(app):
def test_api_update_rule_incr_remove_write_group(app):
def test_api_update_rule_incr_remove_write_groups(app):
"""


def test_api_delete_rule_admin_success(app):
    # ensure admin can delate a rule even if not a member
    pass

def test_api_delete_rule_owner_success(app):
    # ensure that rule owners can delete rule
    pass

def test_api_delete_rule_non_owner_success(app):
    # ensure that non-owner users with write access can delete rule
    pass

def test_api_delete_rule_block(app):
    # ensure that users without write access cannot delete rule
    pass

def test_api_read_resource_success(app):
    # read a test resource that user has access to and ensure it is allowed
    pass

def test_api_read_resource_block(app):
    # read a test resource that user does not have access to and ensure it is
    # blocked
    pass

def test_api_read_resource_sub_dn_success(app):
    # read a sub-dn resource that user had access to and ensure it is allowed
    pass

def test_api_read_resource_sub_dn_block(app):
    # read a sub-dn resource that user does not have access to and ensure it is
    # blocked
    pass

def test_api_write_resource_success(app):
    # write test resource that user has access to and ensure it is allowed
    pass

def test_api_write_resource_block(app):
    # write test resource that user does not have access to and ensure it is
    # blocked
    pass

def test_api_write_resource_sub_dn_success(app):
    # write sub-dn resource that user had access to and ensure it is allowed
    pass

def test_api_write_resource_sub_dn_block(app):
    # write sub-dn resource that user does not have access to and ensure it is
    # blocked
    pass




