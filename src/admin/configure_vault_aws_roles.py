import requests
import os
import boto3
import json

if __name__ == "__main__":
    users_file = "./config/users.json"
    config_file = "./config/install_config.json"
    domino_vault_user = ""
    customer_s3_bucket = ""

    aws_client = boto3.client("iam")
    account_id = str(boto3.client("sts").get_caller_identity().get("Account"))

    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = json.load(f)
            domino_vault_user = config["domino_vault_user"]
            customer_s3_bucket = config["customer_s3_bucket"]

    users = []
    aws_roles = []
    groups_to_users = {}
    aws_roles_to_policies_mapping = {}
    ad_groups = []
    if os.path.exists(users_file):
        with open(users_file) as f:
            j = json.load(f)
            ad_groups = j["AD_GROUPS"]
            groups_to_users = j["AD_GROUP_TO_USER_MAPPING"]
            group_aws_role_mapping = j["AD_GROUP_TO_AWS_ROLE_MAPPING"]

            aws_roles = j["AWS_ROLES"]
            aws_roles_to_policies_mapping = j["AWS_ROLES_TO_POLICIES_MAPPING"]
            for grp, g_users in groups_to_users.items():
                for u in g_users:
                    if not u in users:
                        users.append(u)


    vault_addr = "http://127.0.0.1:8200"
    vault_ns = ""

    with open("./root/etc/vault/token") as f:
        vault_token = f.readline()
    if "VAULT_ADDR" in os.environ:
        vault_addr = os.environ["VAULT_ADDR"]
    if "VAULT_TOKEN" in os.environ:
        vault_token = os.environ["VAULT_TOKEN"]
    if "VAULT_NAMESPACE" in os.environ:
        vault_ns = os.environ["VAULT_NAMESPACE"]

    print(vault_addr)
    print(vault_ns)
    headers = {
        "X-Vault-Token": vault_token,
        "X-Vault-Namespace": vault_ns,
        "Content-Type": "application/json",
    }

    #Configure lease
    configure_lease_url = f"{vault_addr}/v1/aws/config/lease?X-Vault-Token={vault_token}&X-Vault-Namespace={vault_ns}"
    configure_lease_payload = {"lease" : "900", "lease_max" : "72000"}
    payload = json.dumps(configure_lease_payload)
    response = requests.request(
        "POST", configure_lease_url, headers=headers, data=payload
    )
    print(response)
    for r in aws_roles:
        policy_arns = []
        role_policies = aws_roles_to_policies_mapping[r]
        user_creds_url = f"{vault_addr}/v1/aws/roles/{r}"
        for up in role_policies:
            up_arn = f"arn:aws:iam::{account_id}:policy/{up}"
            policy_arns.append(up_arn)
        put_user_role_payload = {
            "credential_type": "federation_token",
            "policy_arns": policy_arns,
            "default_sts_ttl": 900,
            "max_sts_ttl": 72000
        }
        payload = json.dumps(put_user_role_payload)
        print(put_user_role_payload)
        print(user_creds_url)
        response = requests.request(
            "POST", user_creds_url, headers=headers, data=payload
        )
        print(response)

    roles_by_users = {}

    for g in ad_groups:
        users = groups_to_users[g]
        role = group_aws_role_mapping[g]
        for u in users:
            if u not in roles_by_users:
                roles_by_users[u] = []

            print(f"Role for user {u} is {role} and group is {g}")
            aws_role = f"arn:aws:iam::{account_id}:role/{role}"
            roles_by_users[u].append(role)
            # bare_roles_by_users[u].ap

    for u, v in roles_by_users.items():
        user_role_mapping_url = f"{vault_addr}/v1/kv/domino/user/{u}?X-Vault-Token={vault_token}&X-Vault-Namespace={vault_ns}"
        payload = {"roles": v}
        payload = json.dumps(payload)

        print(user_role_mapping_url)
        print(payload)
        response = requests.request(
            "PUT", user_role_mapping_url, headers=headers, data=payload
        )
        print(response)
