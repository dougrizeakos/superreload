

from setuptools import setup, find_packages

setup(
    name='superreload',
    version='0.1.0',
    description='Reload python modules and update old references',
    author='Doug Rizeakos',
    author_email='rizeakad@gmail.com',
    packages=find_packages(include=['superreload', 'superreload.*']),
    install_requires=[
    ],
    setup_requires=['pytest-runner', 'flake8'],
    tests_require=['pytest'],
)

