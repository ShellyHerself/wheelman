'''
This script is part of my appveyor build and upload to pypi system that I've
come up with for my Sigmmma organization.

All the examples of using appveyor seem to be based on the same template
from the Python docs. That template works if you only have one wheel to build.
But if you need to build multiple you face a problem. You can have incomplete
versions uploaded with only some wheels if your projects lack tests.
I really don't like taking that chance. So, this project was born.

MIT License

Copyright (c) 2020 Michelle van der Graaf

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

print('\n\n' + '*'*80)
print('* Initializing Wheelman.')
sys.stdout.flush()

class ExitCodes:
    SUCCESS = 0
    UNSPECIFIED = 1

    MISSING_DEPENDENCIES = 10
    CONFIG_FILE_NOT_FOUND = 11
    CONFIG_YAML_PARSING_ERROR = 12

    BUILD_FAILED_WHEEL = 20
    BUILD_FAILED_SOURCE_DIST = 21

    PIP_FAILURE = 30

    PYPI_FAILURE = 50
    PYPI_MISSING_ENVIRONMENT_VARS = 51
    PYPI_MISSING_CONFIG_VARS = 52

import os
import sys
import shutil

from argparse import ArgumentParser
from traceback import format_exc

try:
    import yaml
    from subprocess import run
except ImportError:
    print(format_exc())
    exit(ExitCodes.ERROR_MISSING_DEPENDENCIES)
except Exception:
    print(format_exc())
    exit(ExitCodes.UNSPECIFIED)


### Argument parsing.

parser = ArgumentParser(
    description='Python wheel and sdist build automation tool.',
    allow_abbrev=False)
parser.add_argument(
    '--target',
    help='Which target to use from the list of targets in the config',
    required=True)
parser.add_argument(
    '--config-file',
    help='What file to read the config from.',
    default=".wheelman.yml",
    required=True)
args.parse_args()


### Config set up.

print('* Loading config file from %s' % args.config_file)

config = {}

try:
    with open(args.config_file) as config:
        config = yaml.load(config.read(), Loader=yaml.Loader)

except yaml.YAMLError, exc:
    print('* ERROR: Config YAML parsing failure.')

    if hasattr(exc, 'problem_mark'):
        mark = exc.problem_mark
        print('* At position: (%s:%s)' % (mark.line+1, mark.column+1))

    exit(ExitCodes.CONFIG_YAML_PARSING_ERROR)

except Exception:
    print("* ERROR: Couldn't load config file.")
    exit(ExitCodes.CONFIG_FILE_NOT_FOUND)


### Preparatory cleanup.

print('\n\n' + '*'*80)
print('* Prepping environment.')

try:
    print('* Deleting potential leftover dist folder.')
    # Just in case for if this is a persistent VM.
    # This is the folder that we upload stuff to pypi from.
    # We want it clean.
    shutil.rmtree("dist")
# TODO: This error should be made specific to if the file was not found.
# Right now a permission error could easily slip through this.
except Exception:
    pass


### Copy the include files into the package.

for name in config['include_files']:
    print('* Copying file %s into folder %s' % (name, config['name']))
    shutil.copyfile(name, "%s/%s" % (config['name'], name))


### Build our targets!

for target in config['targets'].get(args.target, ()):
    # It's a good idea to clean this info up before we do anything else.
    # The files might clash with each other because of different features
    # between python versions.
    print('\n\n' + '*'*80)
    print('* Cleaning up egg-info.')
    sys.stdout.flush()

    try: # It's not mission critical that this succeeds.
         # And the first loop these files shouldn't exist.
         # So we try catch to avoid adding more logic.
        shutil.rmtree("%s.egg-info" % config['name'])
    except Exception:
        pass

    py_exe = target['python']
    print('\n\n' + '*'*80)
    print('* Preparing environment for %s now.' % (py_exe))
    sys.stdout.flush()

    if run([py_exe, '-m', 'pip', 'install', 'wheel']).returncode != 0:
        exit(ExitCodes.PIP_FAILURE)

    print('\n\n' + '*'*80)
    print('* Building for %s now.' % (py_exe))
    sys.stdout.flush()

    # It is suggested to only enable sdist for the highest python version.
    # Because:
    #     1. You can only have one sdist.
    #     2. The sdist doesn't change between python versions.
    #     3. Older versions such as python 3.5 don't understand the arguments
    #        required for markdown descriptions.

    if target.get('sdist', False):
        print('* Doing a source distribution!')
        sys.stdout.flush()
        if run([py_exe, 'setup.py', 'sdist']).returncode != 0:
            print("Failed to build source dist for %s" % py_exe)
            exit(ExitCodes.BUILD_FAILED_SOURCE_DIST)

    # Wheels should be built for every available version that you support.
    # Python <=3.5 is known to crash in online windows build environments
    # because of missing dependencies and microsoft breaking old visual studios.

    if target.get('wheel', False):
        print('* Doing a wheel!')
        sys.stdout.flush()
        if run([py_exe, 'setup.py', 'bdist_wheel']).returncode != 0:
            print("Failed to build wheel for %s" % py_exe)
            exit(ExitCodes.BUILD_FAILED_WHEEL)


### Pypi stuff

pypi_config = config.get("pypi", {})

# You can't just go and upload every commit whilly nilly, default should only
# upload for releases.
only_tags = pypi_config.get('only_upload_tags', True)
is_tag = os.environ.get('APPVEYOR_REPO_TAG', 'false') == 'true'

# Do an upload if we have the right info!

pypi_username = os.environ.get('TWINE_USERNAME', None)
pypi_password = os.environ.get('TWINE_PASSWORD', None)

if (# Only even attempt to upload if we have the right environment vars to do so
    (pypi_username is not None) and
    (pypi_password is not None) and
    # Only upload if on a tag if only_upload_tags is true.
    # Upload either way if not.
    ((only_tags and is_tag) or (not only_tags))):

    print('\n\n' + '*'*80)
    print('* Preparing to upload to twine.')
    print('* Ensuring that twine is installed.')
    sys.stdout.flush()

    pypi_url = pypi_config.get('target_url', '')

    if not pypi_url:
        print('* ERROR: Missing pypi->target_url value in build.yml.')
        exit(ExitCodes.PYPI_MISSING_CONFIG_VARS)

    # Install twine if we don't have it.
    if run([py_exe, '-m', 'pip', 'install', 'twine']).returncode != 0:
        print('* ERROR: Failed to ensure that twine is installed.')
        exit(ExitCodes.PIP_FAILURE)

    # Some build environments don't properly add pip installed packages to PATH
    # So, this is so we can execute using the direct path.
    try:
        from twine.__main__ import __file__ as twine_py
    except ImportError:
        print("* ERROR: Couldn't import twine.")
        exit(ExitCodes.ERROR_MISSING_DEPENDENCIES)

    py_exe = sys.executable

    print('\n\n' + '*'*80)
    print('* Uploading to %s with username %s.' % (pypi_url, pypi_username))
    print('* Using twine located at %s.' % (twine_py))
    sys.stdout.flush()

    if run([py_exe, twine_py, "upload",
            # Let's not lock up our hands off build environment now.
            "--non-interactive",
            "--repository-url", pypi_url,
            "dist/*"]).returncode != 0:
        exit(ExitCodes.PYPI_UPLOAD_FAILURE)

elif (((pypi_username is None) or (pypi_password is None)) and
    pypi_username != pypi_password):
    # If only a username or a password is supplied we can be sure something
    # is fishy.
    print("* ERROR: Only a username or password supplied for pypi")
    sys.stdout.flush()
    exit(ExitCodes.PYPI_MISSING_ENVIRONMENT_VARS)

else:
    # Still inform people to be nice.
    print('\n\n' + '*'*80)
    print('* INFO: Not uploading to pypi.')
    sys.stdout.flush()


exit(ExitCodes.SUCCESS)
