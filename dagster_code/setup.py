from setuptools import setup, find_packages

setup(
    name='dagster_code',
    version='0.1.0',
    packages=find_packages(),
    py_modules=['assets', 'definitions', 'resources'],
)