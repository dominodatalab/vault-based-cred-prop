import boto3
from jinja2 import Environment, FileSystemLoader
import json
from botocore import *


if __name__ == "__main__":
    users_file = "./config/users.json"
    config_file = "./config/install_config.json"
    domino_vault_user = ""
    customer_s3_bucket = ""
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = json.load(f)
            domino_vault_user = config["domino_vault_user"]
            customer_s3_bucket = config["customer_s3_bucket"]

    users = []
    aws_roles = []
    groups_to_users = {}
    aws_roles_to_policies_mapping = {}
    if os.path.exists(users_file):
        with open(users_file) as f:
            j = json.load(f)
            groups_to_users = j["AD_GROUP_TO_USER_MAPPING"]
            group_aws_role_mapping = j["AD_GROUP_TO_AWS_ROLE_MAPPING"]

            aws_roles = j["AWS_ROLES"]
            aws_roles_to_policies_mapping = j["AWS_ROLES_TO_POLICIES_MAPPING"]

            for grp, g_users in groups_to_users.items():
                for u in g_users:
                    if u not in users:
                        users.append(u)

    aws_client = boto3.client("iam")
    aws_account_id = str(boto3.client("sts").get_caller_identity().get("Account"))
    env = Environment(loader=FileSystemLoader("aws_policy_templates"))
    template = env.get_template("BUCKET_SUBFOLDER_LEVEL_POLICY_TEMPLATE.json")

    POLICY_ARN_TEMPLATE = "arn:aws:iam::{aws_account_id}:policy/{policy_name}"
    bucket_sub_folders = j["BUCKET_SUB_FOLDERS"]

    # First detach all policies
    for role in aws_roles:
        try:
            response = aws_client.list_attached_role_policies(RoleName=role)
            for p in response["AttachedPolicies"]:
                aws_client.detach_role_policy(RoleName=role, PolicyArn=p["PolicyArn"])
            # Delete Role
            aws_client.delete_role(RoleName=role)
        except Exception as e:
            print(e)

    # Delete and recreate policies
    for sub_folder in bucket_sub_folders:
        policy_name = f"vault-{sub_folder}_policy"
        try:
            p_arn = POLICY_ARN_TEMPLATE.format(
                aws_account_id=aws_account_id, policy_name=policy_name
            )
            aws_client.delete_policy(PolicyArn=p_arn)
        except Exception as e:
            print(e)
        aws_client.create_policy(
            PolicyName=policy_name,
            PolicyDocument=template.render(
                aws_account=aws_account_id,
                bucket_name=customer_s3_bucket,
                user_name=sub_folder,
            ),
        )

    print("Create Roles")
    template = env.get_template("ASSUME_ROLE_POLICY_DOCUMENT_TEMPLATE.json")
    assume_role_policy_document = template.render(aws_account=aws_account_id)
    for r in aws_roles:
        aws_client.create_role(
            RoleName=r, AssumeRolePolicyDocument=assume_role_policy_document
        )
        print(aws_roles_to_policies_mapping)
        policies = aws_roles_to_policies_mapping[r]
        for policy_name in policies:
            policy_arn = f"arn:aws:iam::{aws_account_id}:policy/{policy_name}".format(
                aws_account_id=aws_account_id, policy_name=policy_name
            )
            aws_client.attach_role_policy(RoleName=r, PolicyArn=policy_arn)
