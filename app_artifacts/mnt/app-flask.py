import subprocess

# This is a sample Python/Flask app showing Domino's App publishing functionality.
# You can publish an app by clicking on "Publish" and selecting "App" in your
# quick-start project.

import json
import flask
from flask import request, redirect, url_for
import numpy as np
import requests as req
import json
from boto3 import Session
from string import Template


class ReverseProxied(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get("HTTP_X_SCRIPT_NAME", "")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ["PATH_INFO"]
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name) :]
        # Setting wsgi.url_scheme from Headers set by proxy before app
        scheme = environ.get("HTTP_X_SCHEME", "https")
        if scheme:
            environ["wsgi.url_scheme"] = scheme
        # Setting HTTP_HOST from Headers set by proxy before app
        remote_host = environ.get("HTTP_X_FORWARDED_HOST", "")
        remote_port = environ.get("HTTP_X_FORWARDED_PORT", "")
        if remote_host and remote_port:
            environ["HTTP_HOST"] = f"{remote_host}:{remote_port}"
        return self.app(environ, start_response)


app = flask.Flask(__name__)
app.wsgi_app = ReverseProxied(app.wsgi_app)


# Homepage which uses a template file
@app.route("/")
def index_page():
    return flask.render_template("index.html")


# Sample redirect using url_for
@app.route("/redirect_test")
def redirect_test():
    return redirect(url_for("another_page"))


# Sample return string instead of using template file
@app.route("/another_page")
def another_page():
    msg = (
        "You made it with redirect( url_for('another_page') )."
        + "A call to flask's url_for('index_page') returns "
        + url_for("index_page")
        + "."
    )
    return msg


@app.route("/random")
@app.route("/random/<int:n>")
def random(n=100):
    random_numbers = list(np.random.random(n))
    return json.dumps(random_numbers)


URL_TEMPLATE = "http://127.0.0.1:5010/awscreds?user-name=$user&project-name=$project&refresh=$refresh"
URL_USER_ONLY_TEMPLATE = (
    "http://127.0.0.1:5010/awscreds?user-name=$user&refresh=$refresh"
)

t = Template(URL_TEMPLATE)
tu = Template(URL_USER_ONLY_TEMPLATE)


@app.route("/readmys3folderAsUser", methods=["GET"])
def readmys3folderAsUser():
    user_only = True
    output_as_string = False
    return get_output(request.headers, user_only, output_as_string)


@app.route("/readmys3folderAsProject", methods=["GET"])
def readmys3folderAsProject():
    user_only = False
    output_as_string = False
    return get_output(request.headers, user_only, output_as_string)


def get_output(headers, user_only=False, as_str=True):
    j = get_creds(headers, user_only)
    no_of_creds = j["no_of_creds"]

    bucket = "domino-test-customer-bucket"
    folders = ["test-user-1", "test-user-2", "test-user-3"]
    out_json = {}

    if no_of_creds > 0:
        keys = j["aws_creds"].keys()
        for k in keys:
            session = Session(
                aws_access_key_id=j["aws_creds"][k]["AWS_ACCESS_KEY_ID"],
                aws_secret_access_key=j["aws_creds"][k]["AWS_SECRET_ACCESS_KEY"],
                aws_session_token=j["aws_creds"][k]["AWS_SESSION_TOKEN"],
            )
            s3 = session.resource("s3")

            arr = []
            for f in folders:
                mykey = f + "/whoami.txt"
                try:
                    obj = s3.Object(bucket, mykey)
                    txt = obj.get()["Body"].read().decode("utf-8")
                    arr.append({"bucket": bucket, "key": mykey, "value": txt})
                except Exception as err:
                    error_string = str(err)
                    arr.append({"bucket": bucket, "key": mykey, "value": error_string})

            out_json[k] = arr

        s = out_json
        if as_str:
            s = json.dumps(out_json)

    return s


def get_creds(headers, user_only=False):
    user = headers.get("Domino-Username")
    param = headers.get("X-Script-Name")
    refresh = False
    project_name = extract_project(param)
    if "Creds-Refresh" in headers:
        refresh = headers.get("Creds-Refresh")

    if not user_only:

        url = t.substitute(user=user, project=project_name, refresh=refresh)
    else:
        url = tu.substitute(user=user, refresh=refresh)
    print(url)
    response = req.get(url)
    j = response.json()
    j["user"] = user
    j["project_name"] = project_name
    return j


def extract_project(param):
    arr = param.split("/")
    project_name = arr[1].replace(" ", "-") + "-" + arr[2].replace(" ", "-")
    return project_name
