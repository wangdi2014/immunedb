from setuptools import setup

setup(name='SLDB',
      version='1.0.5',
      author='Aaron M. Rosenfeld',
      author_email='ar374@drexel.edu',
      packages=[
          'sldb',
          'sldb.api',
          'sldb.common',
          'sldb.conversion',
          'sldb.identification',
          'sldb.trees',
          'sldb.util',
      ],
      scripts=[
          'bin/sldb_clones',
          'bin/sldb_conv_table',
          'bin/sldb_identify',
          'bin/sldb_mt2db',
          'bin/sldb_newick2json',
          'bin/sldb_rest',
      ],
      install_requires=[
          'sqlalchemy>=0.9.8',
          'biopython',
          'bottle',
          'ete2 >= 2.2',
          'distance',
      ],
      license='LICENSE.txt',
      description='Various utilities for Drexel\'s Systems Immunology Lab.')