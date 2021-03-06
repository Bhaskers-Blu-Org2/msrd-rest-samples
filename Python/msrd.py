#!/usr/bin/env python3
""" The MSRD Package Based Submission Client """
import json
from pathlib import Path
from urllib.parse import urljoin

import click
import requests


class Client:
    """
    Example REST API client.

    This client encapsulates the environment and authentication information
    required to use the MSRD REST API, includes the Files API.
    """
    def __init__(self, msrd_url, account_id, api_token):
        self.msrd_url = msrd_url
        self.account_id = account_id
        self.api_token = api_token

        accounts_url = urljoin(self.msrd_url, 'accounts')
        self.account_url = urljoin(accounts_url, self.account_id)

        self.headers = {
            'SpringfieldApiToken': self.api_token,
        }

        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.hooks.update(
            {
                'response': lambda r, *args, **kwargs: print(
                    '{} {} {}'.format(
                        r.status_code,
                        r.reason,
                        r.url
                    )
                )
            }
        )

    def _url(self, fmt, *args, **kwargs):
        """
        Format URL.
        """
        path = fmt.format(*args, **kwargs)
        return urljoin(self.msrd_url, path)

    def account_info(self):
        """
        Get Account Information via a REST Call to the MSRD API.
        """
        url = self._url('api/accounts/{}', self.account_id)
        return self.session.get(url)

    def os_images(self):
        """
        Get Available OS Images for the Account via a REST Call to the MSRD API.
        """
        url = self._url('api/accounts/{}/osimages', self.account_id)
        return self.session.get(url)

    def job_tiers(self):
        """
        Get Available Job Tiers for the Account via a REST Call to the MSRD API.
        """
        url = self._url('api/accounts/{}/jobtiers', self.account_id)
        return self.session.get(url)

    def jobs(self):
        """
        Get Available Job for the Account via a REST Call to the MSRD API.
        """
        url = self._url('api/accounts/{}/jobs', self.account_id)
        return self.session.get(url)

    def upload_file(self, file_path):
        """
        Upload file via a REST Call to the MSRD File PUT API.
        """
        url = self._url('files/accounts/{}/session', self.account_id)
        with open(file_path, 'rb') as file_to_upload:
            return self.session.put(url, data=file_to_upload)

    def submit_job(self, job):
        """
        Submit Job via a REST Call to the MSRD API.
        """
        url = self._url('api/accounts/{}/jobs', self.account_id)
        return self.session.post(url, json=job)


def print_response(response):
    """
    Pretty-Print response data
    """
    try:
        print(json.dumps(response.json(), indent=2))
    except json.JSONDecodeError:
        print(response.text)


DEFAULT_MSRD_URL = 'https://microsoftsecurityriskdetection.com'

MAX_FILE_SIZE = 4194304  # 4 Megabytes.


def upload_file_and_generate_file_info(client, file):
    """
    Generate file information required by the job submission:
        URL: The URL generated by the upload of the resource.
    """
    path = Path(file)
    size = path.stat().st_size

    if size > MAX_FILE_SIZE:
        print('ERROR: file "{}" has byte size {}, which exceeds limit of 4mb'.format(file, size))
        exit(1)

    name = path.name

    # Does not currently return JSON, but a double-quoted URL as text.
    # Remove the double-quotes to avoid errors later on.
    url = client.upload_file(file).text.strip('"')

    return {
        'action': 'DownloadOnly',
        'name': name,
        'url': url,
    }


def update_file_info_in_job(job, file_infos):
    """
    Update the 'setup.package.fileInformations' data in the JSON to append new file information.
    """
    for file_info in file_infos:
        try:
            job['setup']['package']['fileInformations'].append(file_info)
        except (KeyError, TypeError, AttributeError):
            # If we get here, 'setup.package.fileInformations' does not exist yet.
            print('Job file input is missing required setup.package.fileInformations data.')
            exit(1)
    return job


def add_file_info_to_job(client, job, files):
    """
    Update a JSON based job collection to include data for the files on the command
    line by appending the following file information data to the outputted
    'setup.package.fileInformations' data:

    file_information = {
        url: 'URL Generated By Azure for the file.'
        name: 'The original file's base name.'
        action: 'DownloadOnly'
    }
    """
    file_info = []

    # Max file size is 4mb.
    for file in files:
        info = upload_file_and_generate_file_info(client, file)

        file_info.append(info)

    if file_info:
        job = update_file_info_in_job(job, file_info)

    return job


@click.group()
@click.option('msrd_url',
              '-u', '--url',
              default=DEFAULT_MSRD_URL,
              envvar='MSRD_URL',
              prompt='MSRD base URL?')
@click.option('account_id',
              '-a', '--account',
              envvar='MSRD_ACCOUNT',
              prompt='Account ID?')
@click.option('api_token',
              '-t', '--token',
              envvar='MSRD_TOKEN',
              prompt='API Token?')
@click.pass_context
def main(ctx, msrd_url, account_id, api_token):
    """Construct the MSRD client and continue."""
    ctx.obj = Client(msrd_url, account_id, api_token)


@main.command()
@click.pass_obj
def account_info(client):
    """Get and print account information."""
    print_response(client.account_info())


@main.command()
@click.pass_obj
def os_images(client):
    """Get and print available os images."""
    print_response(client.os_images())


@main.command()
@click.pass_obj
def job_tiers(client):
    """Get and print job tiers available to the account."""
    print_response(client.job_tiers())


@main.command()
@click.pass_obj
def jobs(client):
    """Get and print jobs available to the account."""
    print_response(client.jobs())


@main.command()
@click.option('file_path', '-f', '--file')
@click.pass_obj
def upload_file(client, file_path):
    """Upload single file and print resulting generated URL."""
    print_response(client.upload_file(file_path))


@main.command()
@click.option('job_path', '-j', '--job', prompt='Path to job JSON')
@click.option('output_job_path',
              '-o', '--out_job_file',
              required=False,
              default=None)  # Only Print Instead by default.
@click.argument('files', nargs=-1)
@click.pass_obj
def submit(client, job_path, output_job_path, files):
    """
    Submit a new Fuzzing Job via the MSRD REST API.
    """
    with open(job_path) as input_job_file:
        job = json.load(input_job_file)

    job = add_file_info_to_job(client, job, files)

    if output_job_path:
        with open(output_job_path) as out_file:
            json.dump(job, out_file, indent=2)

    print_response(client.submit_job(job))


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
