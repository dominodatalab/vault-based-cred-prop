import sys
import os
import boto3
from jinja2 import Environment, FileSystemLoader
import json
from botocore import *

if __name__ == "__main__":
    creds_file = "./aws_creds/creds.json"
    config_file = "./config/install_config.json"

    domino_vault_user = ""
    customer_s3_bucket = ""
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = json.load(f)
            domino_vault_user = config["domino_vault_user"]
            customer_s3_bucket = config["customer_s3_bucket"]

    access_key_id = ""

    if os.path.exists(creds_file):
        with open(creds_file, "r") as f:
            creds_json = json.load(f)
            if "AccessKeyId" in creds_json:
                access_key_id = creds_json["AccessKeyId"]

    if len(sys.argv) > 1:
        domino_vault_user = sys.argv[2]
    if len(sys.argv) > 2:
        customer_s3_bucket = sys.argv[3]
    if len(sys.argv) > 3:
        access_key_id = sys.argv[1]

    aws_client = boto3.client("iam")
    aws_account_id = str(boto3.client("sts").get_caller_identity().get("Account"))
    print("Delete user " + domino_vault_user + " if user exists")
    try:
        aws_client.get_user(UserName=domino_vault_user)
        Metadata = aws_client.list_access_keys(UserName=domino_vault_user)

        print(Metadata["AccessKeyMetadata"])
        for a in Metadata["AccessKeyMetadata"]:
            aws_client.delete_access_key(
                UserName=domino_vault_user, AccessKeyId=a["AccessKeyId"]
            )
    except Exception as e:
        print(e)
        print("Continue because there may be no access keys")
    try:
        aws_client.get_user(UserName=domino_vault_user)

        policies = aws_client.list_user_policies(UserName=domino_vault_user)[
            "PolicyNames"
        ]
        # First delete these policies
        for p in policies:
            aws_client.delete_user_policy(UserName=domino_vault_user, PolicyName=p)
        aws_client.delete_user(UserName=domino_vault_user)
    except Exception as e:
        print(e)
        print("User does not exist- Nothing to delete")

    print("Creating user " + domino_vault_user)

    aws_client.create_user(UserName=domino_vault_user)
    # Create a Vault Policy

    # Give the user permisssions to perform STS actions
    env = Environment(loader=FileSystemLoader("aws_policy_templates"))
    template = env.get_template("VAULT_USER_POLICY_TEMPLATE.json")
    vault_domino_policy = template.render(
        aws_account=aws_account_id, vault_user=domino_vault_user
    )
    template = env.get_template("PERMISSIONS_BOUNDARY_POLICY_TEMPLATE.json")
    permissions_boundary_policy = template.render(
        aws_account=aws_account_id, bucket_name=customer_s3_bucket
    )

    aws_client.put_user_policy(
        UserName=domino_vault_user,
        PolicyName="VAULT_DOMINO_USER",
        PolicyDocument=vault_domino_policy,
    )
    aws_client.put_user_policy(
        UserName=domino_vault_user,
        PolicyName="CUSTOMER_BOUNDARY_PERMISSION",
        PolicyDocument=permissions_boundary_policy,
    )

    # Create user access keys
    user_creds = aws_client.create_access_key(UserName=domino_vault_user)["AccessKey"]
    print(user_creds)
    u = {
        "UserName": "vault-domino",
        "AccessKeyId": user_creds["AccessKeyId"],
        "SecretAccessKey": user_creds["SecretAccessKey"],
    }
    with open(creds_file, "w") as f:
        f.write(json.dumps(u))
