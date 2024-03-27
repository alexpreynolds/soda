# -*- coding: utf-8 -*-

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="soda-gallery",
    version="1.2.0",
    author="Alex Reynolds",
    author_email="alexpreynolds@gmail.com",
    description="Python-based UCSC genome browser gallery generator",
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=[
        "requests>=2.25.1",
        "certifi>=2024.2.2",
        "beautifulsoup4>=4.9.3",
        "Jinja2>=3.0.1",
        "pdfminer>=20191125",
        "pdfrw>=0.4",
        "requests_kerberos>=0.12.0"
    ],                                             
    url="https://github.com/alexpreynolds/soda",  
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Bio-Informatics"
    ],
    entry_points={
        "console_scripts": [
            "soda = soda.soda:main",
        ],
    },
)
