# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name="django-pg-extensions",
    version="0.1.8",
    description="Extensions for Django to fully utilize PostgreSQL.",
    author="Apostolos Bessas",
    author_email="mpessas@gmail.com",
    packages=["djangopg", "djangopg.postgresql_psycopg2", ],
    install_requires=["Django==1.6.11", ],
    tests_require=["django-discover-runner", "mock", ]
)
