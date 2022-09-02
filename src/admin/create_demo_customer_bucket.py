import sys
import boto3
import json
import os

if __name__ == "__main__":

    creds_file = "./aws_creds/creds.json"
    config_file = "./config/install_config.json"
    users_file = "./config/users.json"

    customer_s3_bucket = ""
    domino_vault_user = ""
    customer_s3_bucket = ""
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    if len(sys.argv) > 2:
        users_file = sys.argv[2]

    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = json.load(f)
            customer_s3_bucket = config["customer_s3_bucket"]
            domino_vault_user = config["domino_vault_user"]

    users = []
    if os.path.exists(users_file):
        with open(users_file) as f:
            j = json.load(f)
            groups_to_users = j["AD_GROUP_TO_USER_MAPPING"]
            for grp, g_users in groups_to_users.items():
                for u in g_users:
                    if not u in users:
                        users.append(u)
    # Create S3 bucket
    s3_client = boto3.client("s3")
    s3 = boto3.resource("s3")
    bucket = s3.Bucket(customer_s3_bucket)
    try:
        print("Deleting bucket {bucket}".format(bucket=customer_s3_bucket))
        print("     First empty bucket {bucket}".format(bucket=customer_s3_bucket))
        bucket.objects.all().delete()
        print("     Next delete bucket {bucket}".format(bucket=customer_s3_bucket))
        s3_client.delete_bucket(Bucket=customer_s3_bucket)
    except Exception as e:
        print(e)

    print("Create bucket {bucket}".format(bucket=customer_s3_bucket))
    s3_client.create_bucket(
        Bucket=customer_s3_bucket,
        CreateBucketConfiguration={"LocationConstraint": s3_client.meta.region_name},
    )

    print("Add user keys to bucket {bucket}".format(bucket=customer_s3_bucket))
    s3 = boto3.resource("s3")
    print(users)
    for u in users:
        key = "{}/whoami.txt".format(u)
        value = "I am {}".format(u)
        print(
            "Adding key/value {key} = {value} to bucket {bucket}".format(
                key=key, value=value, bucket=customer_s3_bucket
            )
        )
        s3.Object(customer_s3_bucket, key).put(Body=value)
