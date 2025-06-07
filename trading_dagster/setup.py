from setuptools import find_packages, setup

setup(
    name="trading_dagster",
    packages=find_packages(exclude=["trading_dagster_tests"]),
    install_requires=[
        "dagster",
    ],
    extras_require={"dev": ["dagster-webserver", "pytest"]},
)
