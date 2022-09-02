#!/usr/bin/env python
import logging
import sys
from datetime import datetime, timedelta
import time
import threading
import os
import json
import flask
import configparser
import requests
from jproperties import Properties


app = flask.Flask(__name__)
app.config["DEBUG"] = True

MAX_TIME_TO_WAIT_FOR_TOKEN_TO_APPEAR = 30
GET_ROLES_ENDPOINT = "{vault_endpoint}/v1/kv/domino/user/{user_id}"
GET_AWS_CREDS_ENDPOINT = "{vault_endpoint}/v1/aws/creds/{role}"
LIST_LEASES_ENDPOINT = "{vault_endpoint}/v1/sys/leases/lookup/aws/creds/{role}"
RENEW_LEASE = "{vault_endpoint}/v1/sys/leases/renew"
REVOKE_LEASE = "{vault_endpoint}/v1/sys/leases/revoke"
AWS_CREDS_PATH = "etc/.aws/"


def get_vault_headers():
    headers = {"X-Vault-Token": vault_token, "X-Vault-Namespace": vault_namespace}
    return headers


@app.route("/allroles", methods=["GET"])
def get_roles():
    url = GET_ROLES_ENDPOINT.format(
        vault_endpoint=vault_endpoint, user_id=config_domino_user_name
    )
    default_user_url = GET_ROLES_ENDPOINT.format(
        vault_endpoint=vault_endpoint, user_id=config_default_domino_user_name
    )
    logging.info("Invoking endpoint " + url)
    user_roles = requests.get(url, headers=get_vault_headers())
    roles = []
    if user_roles.status_code == 200:
        data = json.loads(user_roles.content)
        logging.info("Get AWS Roles for this user " + config_domino_user_name)
        print(url)
        roles = data["data"]["roles"]
    else:
        logging.info(
            "No roles mapping found. Using default roles mapping for user "
            + config_domino_user_name
        )
        user_roles = requests.get(default_user_url, headers=get_vault_headers())
        if user_roles.status_code == 200:
            data = json.loads(user_roles.content)
            logging.info("Get AWS Roles for this user " + config_domino_user_name)
            roles = data["data"]["roles"]
        else:
            # No default user mappings configured
            pass
    logging.debug(f"Roles are str{roles}")
    return roles


def get_new_creds(role):
    url = GET_AWS_CREDS_ENDPOINT.format(vault_endpoint=vault_endpoint, role=role)
    logging.info("Invoking endpoint " + url)
    result = requests.get(url, headers=get_vault_headers())
    lease_content = json.loads(result.content)
    if result.status_code == 200:
        expiry_time = datetime.now().timestamp() + lease_content["lease_duration"]
        lease_content["expiry_time"] = expiry_time
        my_aws_creds[role] = lease_content
        add_to_aws_credentials_file(
            role,
            lease_content["data"]["access_key"],
            lease_content["data"]["secret_key"],
            lease_content["data"]["security_token"],
            expiry_time,
        )
    else:
        logging.info("Error running endpoint " + url + " " + json.dumps(result.content))
    return lease_content


def renew_creds(role, lease_id):
    current_time = datetime.now().timestamp()
    url = RENEW_LEASE.format(vault_endpoint=vault_endpoint)
    logging.info("Invoking endpoint " + url)
    result = requests.put(
        url,
        data={"lease_id": lease_id, "increment": config_lease_inc},
        headers={"X-Vault-Token": vault_token},
    )
    data = {}
    if result.status_code == 200:
        data = json.loads(result.content)
        expiry_time = current_time + data["lease_duration"]
        my_aws_creds[role]["expiry_time"] = expiry_time
        logging.debug("Renewed lease id " + lease_id)
        update_credentials_file_with_expiry_time(role, expiry_time)
    else:
        logging.info("Error renewing lease id " + lease_id)
        logging.info("Error running endpoint " + url + " " + json.dumps(result.content))
    return data


def add_to_aws_credentials_file(
    role, access_key, secret_key, security_token, expiry_time
):
    logging.debug("writing to aws creds file " + role)
    aws_credentials_path = os.path.join(base_path, AWS_CREDS_PATH, "credentials")
    config = configparser.ConfigParser()
    config.read(aws_credentials_path)
    if role not in config.sections():
        config.add_section(role)
    config[role]["aws_access_key_id"] = access_key
    config[role]["aws_secret_access_key"] = secret_key
    config[role]["expiry_time"] = str(expiry_time)

    if security_token is not None:
        config[role]["aws_session_token"] = security_token
    config.write(open(aws_credentials_path, "w"), space_around_delimiters=False)


def update_credentials_file_with_expiry_time(role, expiry_time):
    logging.debug(f"Updating aws creds file for {role} with expiry time {expiry_time}")
    aws_credentials_path = os.path.join(base_path, AWS_CREDS_PATH, "credentials")
    config = configparser.ConfigParser()
    config.read(aws_credentials_path)
    if role in config.sections():
        config[role]["expiry_time"] = str(expiry_time)
    config.write(open(aws_credentials_path, "w"), space_around_delimiters=False)


@app.route("/renew_all", methods=["GET"])
def refresh_aws_creds():
    current_time = datetime.now().timestamp()
    roles = get_roles()
    if roles is None:
        roles = []
    logging.debug(f"User roles {str(roles)}")
    if isinstance(roles, str):
        roles = [roles]
    logging.debug("Checking if credentials need to be refreshed")
    for role in roles:
        data = None
        if role in my_aws_creds:
            data = my_aws_creds[role]
        if data is None:
            logging.debug(f"Generate roles for role name {role}")
            data = get_new_creds(role)
            data["create_time"] = current_time
            my_aws_creds[role] = data
        else:
            if data["renewable"]:
                time_to_expire = current_time - data["expiry_time"]
                str(time_to_expire)
                if time_to_expire > refresh_threshold_in_seconds:
                    logging.debug(
                        f"Diff between current time and expiry time is {time_to_expire}"
                    )
                    logging.debug(f"Renewing the credentials for role {role}")
                    renew_creds(role, data["lease_id"])
    return {}


def revoke_creds(lease_id):
    url = REVOKE_LEASE.format(vault_endpoint=vault_endpoint)
    logging.debug(f"Invoking revoke endpoint {url}")
    result = requests.put(
        url, data={"lease_id": lease_id}, headers={"X-Vault-Token": vault_token}
    )
    if result.status_code == 204:
        logging.debug("Revoked lease " + " " + lease_id)
    else:
        logging.debug("Error revoking lease " + " " + lease_id)


@app.route("/revoke_all", methods=["GET"])
def revoke_all_creds():
    logging.debug("Revoking Credentials")
    for key, data in my_aws_creds.items():
        revoke_creds(data["lease_id"])
    return {}


def refresh_thread():
    while True:
        refresh_aws_creds()
        logging.debug(
            "Refresh thread sleeping for (in secs) " + str(polling_interval_in_seconds)
        )
        time.sleep(polling_interval_in_seconds)


# The first call to /heathz from the start_runner thread activates the refresh thread
@app.before_first_request
def activate_job():
    refresher_thread = threading.Thread(
        target=refresh_thread,
        args=(),
    )
    refresher_thread.start()
    logging.debug("Thread responsible for refreshing AWS Creds started")


@app.route("/healthz", methods=["GET"])
def healthz():
    return {}


def start_runner():
    def start_loop():
        not_started = True
        while not_started:
            logging.debug("In start loop")
            url = "http://127.0.0.1:" + str(port_no) + "/healthz"
            logging.debug(f"Invoking {url}")
            try:
                r = requests.get(url)
                if r.status_code == 200:
                    logging.debug("Server started, quiting start_loop")
                    not_started = False
                logging.debug(f"Status code when invoking {url} {r.status_code}")
            except:
                logging.debug(f"Not yet started - {url}")
            # Wait 2 seconds before retrying or proceeding
            time.sleep(2)

    logging.debug("Started runner")
    thread = threading.Thread(target=start_loop)
    thread.start()


def get_domino_user_name():
    configs = Properties()
    with open(os.path.join(base_path, "etc/labels", "labels"), "rb") as read_prop:
        configs.load(read_prop)
        user_name = configs.get("dominodatalab.com/starting-user-username").data
    return user_name


def configure_app():
    global app_config
    global vault_token
    global vault_namespace
    global polling_interval_in_seconds
    global refresh_threshold_in_seconds
    global vault_endpoint
    global config_domino_user_name
    global config_default_domino_user_name
    global config_lease_inc

    config_domino_user_name = get_domino_user_name()
    with open(
        os.path.join(base_path, "etc/config", "dynamic-aws-creds-config"), "r"
    ) as file:
        data = file.read()
        app_config = json.loads(data)
    print(app_config)
    polling_interval_in_seconds = app_config["polling_interval_in_seconds"]
    refresh_threshold_in_seconds = app_config["refresh_threshold_in_seconds"]
    vault_endpoint = app_config["vault_endpoint"]
    vault_namespace = app_config["vault_namespace"]
    if "default_user" in app_config:
        config_default_domino_user_name = app_config["default_user"]
    config_lease_inc = app_config["lease_increment"]

    with open(os.path.join(base_path, "etc/vault", "token"), "r") as file:
        vault_token = file.read().replace("\n", "")


base_path = ""
app_config = {}

vault_token = ""
vault_namespace = ""
vault_endpoint = ""
config_lease_inc = 3600

port_no = 5003

polling_interval_in_seconds = 300
refresh_threshold_in_seconds = 60

config_domino_user_name = ""
config_default_domino_user_name = ""

my_aws_creds = {}

if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    # base_path = os.path.join(os.getcwd() , '../test_pod_fs/')
    base_path = sys.argv[1]
    port_no = 5010
    if len(sys.argv) > 2:
        port_no = int(sys.argv[2])

    logs_file = os.path.join(base_path, "var/log/vault", "app.log")

    lvl: str = logging.getLevelName(os.environ.get("LOG_LEVEL", "WARNING"))
    logging.basicConfig(
        filename=logs_file,
        filemode="a",
        format="%(asctime)s - %(message)s",
        level=lvl,
        datefmt="%H:%M:%S",
    )
    logging.info("Base path " + base_path)
    log = logging.getLogger("werkzeug")

    configure_app()
    # Do everything once as initialization step
    # First AWS_Credentials_Fetch
    # refresh_aws_creds()
    # First JIT Sessions
    # First AWS Credentials

    # Now start refresher thread

    # Now start flask server
    start_runner()
    logging.debug("Starting Flask")
    app.run(debug=True, host="0.0.0.0", port=port_no)
    stop_threads = True

    logging.debug("Now stopping")
    logging.shutdown()
